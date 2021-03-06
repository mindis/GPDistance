#!/usr/bin/env python

"""This module provides functionality implementing an absorbing Markov
chain. It can be used to calculate the expected length of a random
walk between any two points in a space, given the transition matrix on
the space. Also the lowest-cost path (treating low transition
probabilities as high edge traversal costs) and the shortest path (in
number of steps, disregarding probabilities)."""

import numpy as np
import scipy.stats, scipy.misc
import random
import sys
import os
import itertools
from collections import OrderedDict
import matplotlib.pyplot as plt
import cPickle as pickle

# this import is from
# http://www.pysal.org/library/spatial_dynamics/ergodic.html: it
# implements the mean-first-passage-time algorithm, also known as the
# first-mean-passage-time, as described in Kemeny, John, G. and
# J. Laurie Snell (1976) Finite Markov Chains. Springer-Verlag,
# Berlin.
import ergodic

def analyse_random_walk(dirname):
    """Java code will write out a list of sampled lengths of random
    walks between nodes i and j. A single file, each line containing
    the tree i, tree j, then the list of samples. Analyse the
    basics."""

    n = 20
    f = open(dirname + "/MFPT_random_walking_samples.dat")
    x_mean = np.zeros((n, n))
    x_var = np.zeros((n, n))
    x_len = np.zeros((n, n), dtype=int)
    i = 0
    j = 0
    for line in f:
        t0, t1, samples = line.split(":")
        samples = np.array(map(int, samples.strip().split(" ")))
        x_mean[i, j] = np.mean(samples)
        x_var[i, j] = np.std(samples)
        x_len[i, j] = len(samples)
        i += 1
        if i == n:
            i = 0
            j += 1
    print(x_mean)
    print(x_var)
    print(x_len)

def estimate_MFPT_with_supernode(dirname):
    """Given a directory, go in there and get all the files under
    TP_supernode_estimates. For each, run the algorithm to get mfpt,
    and from the result extract the (0, 1) and (1, 0) values. Find out
    which trees they correspond to. Then correlate between all these
    values and the values calculated by exact MFPT given the complete
    TP matrix."""
    n = 50
    all_trees = open(dirname + "/all_trees.dat").read().strip().split("\n")
    estimate = np.zeros(2 * n)
    exact = np.genfromtxt(dirname + "/MFPT.dat")
    exact_extract = np.zeros(2 * n)
    ted = np.genfromtxt(dirname + "/TED.dat")
    ted_extract = np.zeros(2 * n)
    for i in range(n):
        d = read_transition_matrix(dirname + "/TP_supernode_estimates/"
                                   + str(i) + "_TP_estimates.dat")
        m = get_mfpt(d)
        t, s = open(dirname + "/TP_supernode_estimates/"
                    + str(i) + "_trees.dat").read().strip().split("\n")
        ti = all_trees.index(t)
        si = all_trees.index(s)
        estimate[2*i] = m[0, 1]
        estimate[2*i+1] = m[1, 0]
        exact_extract[2*i] = exact[ti, si]
        exact_extract[2*i+1] = exact[si, ti]
        ted_extract[2*i] = ted[ti, si]
        ted_extract[2*i+1] = ted[si, ti]
    np.savetxt(dirname + "/MFPT_supernode_estimate.dat", estimate)
    np.savetxt(dirname + "/TED_extract_for_supernode_estimate.dat", ted_extract)
    np.savetxt(dirname + "/MFPT_exact_for_supernode_estimate.dat", exact_extract)

def normalise_by_row(d):
    """Normalise an array row-by-row, ie make each row sum to 1. This
    is useful when creating transition matrices on sub-graphs, or
    randomly-generating transition matrices, or for matrices created
    using a hill-climbing adjustment to transition probabilies: in
    such cases, the transition probabilities are adjusted to take
    account of fitness, so "bad" transitions (to worse fitness) are
    made less likely to be accepted, meaning that each row no longer
    sums to 1. By renormalising we get the true probability after (if
    necessary) multiple rounds of rejection and finally one
    acceptance."""
    # np.sum(d, 1).reshape((len(d), 1)) is the column of row-sums
    return d / np.sum(d, 1).reshape((len(d), 1))

def make_random_matrix(n):
    """Make a random transition matrix on n points."""
    tm = np.random.random((n, n))
    return normalise_by_row(tm)

def make_random_binary_matrix(n, p):
    """n is the number of nodes, p the probability of each possible
    edge existing. A graph with isolated nodes or isolated
    subcomponents will break the MFPT algorithm, so we have to be
    careful. There are algorithms to guarantee connectivity, but the
    quick-n-dirty solution is to keep generating until we get a
    connected graph. If we fail after (say) 100 attempts, it could be
    because the choice of n and p tend to give unconnected graphs, so
    just fail.
    """

    i = 0
    while i < 100:
        d = np.array(np.random.random((n, n)) < p, dtype=float)
        d = normalise_by_row(d)
        steps = floyd_warshall_nsteps(d)
        if np.all(np.isfinite(steps)):
            return d

def map_infinity_to_large(w):
    """If there any infinities in w, they can cause numerical errors.
    In some situations, it can be adequately solved by putting in an
    arbitrary large value instead. We map to 100 times the largest
    finite value in w."""
    is_w_finite = np.isfinite(w)
    realmax = np.max(w[is_w_finite])
    np.copyto(w, realmax * 100.0, where=~is_w_finite)

def mean_mfpt(n, p):
    """n is the number of nodes, p the probability of each possible
    edge existing. idea is to see if there's a correlation between
    mean mfpt and p."""
    m = make_random_binary_matrix(n, p)
    mfpt = get_mfpt(m)
    mean_mfpt = np.mean(mfpt)
    # get mean mfpt off-diagonal -- this formula works because the
    # diagonal is zero
    mean_mfpt_distinct = np.sum(mfpt) / (len(mfpt)**2 - len(mfpt))
    ne = np.sum(m>0)
    return m, ne, mfpt, mean_mfpt, mean_mfpt_distinct

def test_mean_mfpt():
    reps = 50
    for n in [100]:
        for p in [0.05, 0.1, 0.15, 0.2]:
            for rep in range(reps):
                m, ne, mfpt, mean, mean_distinct = mean_mfpt(n, p)
                print("%d %f" % (ne, mean_distinct))

def make_absorbing(tm, dest):
    """Given a transition matrix, disallow transitions away from the
    given destination -- ie make it an absorbing matrix."""
    e = np.zeros(len(tm))
    e[dest] = 1
    tm[dest, :] = e

def MSTP_wrapper(dirname):
    x = np.genfromtxt(dirname + "/TP.dat")
    for i in [10, 100]:
        mstp = MSTP_max_n_steps(x, i)
        dmstp = -np.log(mstp)
        np.savetxt(dirname + "/D_MSTP_" + str(i) + ".dat", dmstp)

def MSTP_max_n_steps(x, n=10):
    """The probability of reaching state j, starting from state i, in
    n steps or fewer. Loops are allowed, hence even if n > number of
    states, these probabilities don't reach 1 in general."""
    L = len(x)
    mstp = np.eye(L)
    for i in range(L):
        xi = x.copy()
        make_absorbing(xi, i)
        # the ith column is copied from the ith column of A^n, where A
        # is absorbing in state i
        mstp[:, i] = np.linalg.matrix_power(xi, n)[:, i]
        print i
    return mstp

def read_transition_matrix(filename):
    """Read a transition matrix from a file and return. The matrix
    will have been written in the right format by some Java code."""
    d = np.genfromtxt(filename)
    return d

def check_row_sums(d):
    """Check that each row sums to 1, since each row is the
    out-probabilities from a single individual. Allow the small margin
    of error used by allclose()."""
    return np.allclose(np.ones(len(d)), np.sum(d, 1))

def is_positive_definite(x):
    """This is supposed to be fairly efficient. From
    http://stackoverflow.com/questions/16266720/find-out-if-matrix-is-positive-definite-with-numpy"""
    try:
        L = np.linalg.cholesky(x)
        return True
    except np.linalg.LinAlgError:
        return False

def kernel_to_distance(k):
    """Given a kernel, ie a symmetric positive definite matrix of
    similarities between elements, produce a distance."""
    if not is_symmetric(k):
        raise ValueError("k is not symmetric")
    if not is_positive_definite(k):
        raise ValueError("k is not positive definite")
    kxx = np.diag(k).reshape((len(k), 1)) * np.ones_like(k)
    kyy = np.diag(k) * np.ones_like(k)
    return np.sqrt(kxx + kyy - k - k.T)

def set_self_transition_zero(x):
    """Set cost/length of self-transition to zero."""
    np.fill_diagonal(x, 0.0)

def get_mfpt(x):
    """Calculate mean-first-passage time of a given transition
    matrix. Set self-transitions to zero. Note that the pysal code
    (ergodic.py) calls it "first-mean-passage-time"."""
    # NB! The ergodic code expects a matrix, not a numpy array. Breaks
    # otherwise.
    x = np.matrix(x)
    x = np.array(ergodic.fmpt(x))
    set_self_transition_zero(x)
    return x

def test_matrix_size(n):
    """Test how big the tm can be before get_mfpt becomes
    slow. n = 4000 is fine, n = 10000 starts paging out (at least 30
    minutes)."""
    d = make_random_matrix(n)
    mfpt = get_mfpt(d)
    print("min", np.min(mfpt))
    print("max", np.max(mfpt))

def invert_probabilities(adj):
    """Convert a probability into an edge traversal cost. It's ok to
    ignore runtime floating point problems here, because they're only
    due to zero-probabilities, which result in infinite edge-traversal
    costs, which is what we want. Restore the "raise" behaviour
    afterward."""
    old = np.seterr(divide='ignore')
    retval = -np.log(adj)
    np.seterr(**old)
    return retval

def deinvert_probabilities(adj):
    """Convert an edge traversal cost into a probability."""
    return np.exp(-adj)

def test_floyd_warshall_random_data(n):
    """Test."""
    adj = make_random_matrix(n)
    return floyd_warshall_probabilities(adj)

def floyd_warshall_probabilities(adj):
    """For this to be useful, need to invert the transition matrix
    probabilities p somehow, so that low probabilities cause high edge
    traversal costs. See invert_ and deinvert_probabilities."""
    x = invert_probabilities(adj)
    x = floyd_warshall(x)
    set_self_transition_zero(x)
    return x

def floyd_warshall(adj):
    """Finds the shortest path between all pairs of nodes. For this to
    be useful, the edge weights have to have the right semantics: a
    small transition probability implies a large edge weight
    (cost). So if your edge weights are probabilities, use
    floyd_warshall_probabilities() instead: it performs the
    conversion.

    Concerning matrix size: n = 1000 works fine, n = 4000 starts
    paging out (at least 10 minutes) on my machine."""
    # from
    # http://www.depthfirstsearch.net/blog/2009/12/03/computing-all-shortest-paths-in-python/
    n = len(adj)
    for k in range(n):
        adj = np.minimum(adj, np.add.outer(adj[:,k],adj[k,:]))
    return adj


def floyd_warshall_nsteps(adj):
    """Disregard the transition probabilities, other than to see
    whether an edge traversal is allowed or not. Calculate the number
    of steps required to get from each point to each other."""
    x = discretize_probabilities(adj)
    x = floyd_warshall(x)
    set_self_transition_zero(x)
    return x

def discretize_probabilities(d):
    """Set the edge cost to 1 if there is a nonzero probability, and
    to infinity if there is a zero probability."""
    retval = np.ones_like(d, dtype=float)
    inf = np.infty
    for i in range(len(d)):
        for j in range(len(d)):
            if not d[i, j] > 0.0:
                retval[i, j] = inf
    return retval

def get_dtp(t):
    """Get D_TP, the distance based on transition probability. D_TP(x,
    y) is the log of TP(x, y), for x != y."""
    x = invert_probabilities(t)
    set_self_transition_zero(x)
    return x

def get_symmetric_version(m):
    """Given an asymmetric matrix, return the symmetrized version,
    which is the mean of the matrix and its transpose."""
    return 0.5 * (m + m.T)

def write_symmetric_remoteness(dirname):
    """Read in the D_TP matrix and the MFPT one, and write out the
    symmetric versions."""
    dtp = np.genfromtxt(dirname + "/D_TP.dat")
    mfpt = np.genfromtxt(dirname + "/MFPT.dat")
    sdtp = get_symmetric_version(dtp)
    ct = get_symmetric_version(mfpt)
    # SD_TP is symmetric transition probability distance
    np.savetxt(dirname + "/SD_TP.dat", sdtp)
    # CT stands for commute time
    np.savetxt(dirname + "/CT.dat", ct)

def get_steady_state(tp):
    """Given a transition probability matrix, use ergodic.steady_state
    to calculate the long-run steady-state, which is a vector
    representing how long the system will spend in each state in the
    long run. If not uniform, that is a bias imposed by the operator
    on the system."""
    import ergodic
    ss = np.array(ergodic.steady_state(np.matrix(tp)))
    ss = np.real(ss) # discard zero imaginary parts
    ss = ss.T[0] # not sure why it ends up with an extra unused dimension
    return ss

def is_symmetric(x):
    return np.allclose(x, x.T)

def operator_difference(x, y):
    """The difference between two mutation operators could be measured
    as the mean absolute difference between their transition
    matrices."""
    return np.mean(np.abs(x - y))

def read_and_get_dtp_mfpt_sp_steps(dirname):

    if os.path.exists(dirname + "/TP_nonnormalised.dat"):
        t = read_transition_matrix(dirname + "/TP_nonnormalised.dat")
        # it's a non-normalised matrix, possibly representing a
        # uniformly sampled sub-graph, a hill-climb-sampled graph, or
        # similar.
        t = normalise_by_row(t)
        outfilename = dirname + "/TP.dat"
        np.savetxt(outfilename, t)
    else:
        t = read_transition_matrix(dirname + "/TP.dat")
        check_row_sums(t)

    # This gets D_TP, which is just the transition probability inverted
    d = get_dtp(t)
    outfilename = dirname + "/D_TP.dat"
    np.savetxt(outfilename, d)

    # This gets the mean first passage time, ie the expected length of
    # a random walk.
    f = get_mfpt(t)
    outfilename = dirname + "/MFPT.dat"
    np.savetxt(outfilename, f)

    # This gets the cost of the shortest path between pairs. The cost
    # of an edge is the negative log of its probability.
    h = floyd_warshall_probabilities(t)
    outfilename = dirname + "/SP.dat"
    np.savetxt(outfilename, h)

    # this gets the minimum number of steps required to go between
    # pairs, disregarding probabilities. Only interesting if some
    # edges are absent (ie edge probability is zero).
    p = floyd_warshall_nsteps(t)
    outfilename = dirname + "/STEPS.dat"
    np.savetxt(outfilename, p)



############################################################
# GA (bitstring) stuff
############################################################

def hamming_distance(x, y):
    return np.sum(x != y)

def generate_ga_tm(length, pmut=None):
    """For a bitstring (genetic algorithm) representation of a given
    length, generate a transition matrix with the mutation probability
    pmut. Also generate the Hamming distances. If pmut=None (default),
    exactly one bitflip is performed per individual, rather than using
    a per-gene mutation probability."""

    tm = np.zeros((2**length, 2**length))
    hm = np.zeros((2**length, 2**length))
    for i, indi in enumerate(itertools.product(*[(0, 1) for x in range(length)])):
        indi = np.array(indi, dtype='bool')
        for j, indj in enumerate(itertools.product(*[(0, 1) for y in range(length)])):
            indj = np.array(indj, dtype='bool')
            h = hamming_distance(indi, indj)
            hm[i][j] = h
            if pmut is None:
                if h == 1:
                    tm[i][j] = 1.0 / length # there are length inds at hamming distance 1
                    # else leave it at zero
            else:
                tm[i][j] = (pmut ** h) * ((1.0 - pmut) ** (length - h))
    return tm, hm

def nCk(n, k):
    """n-choose-k"""
    return scipy.misc.comb(n, k, True)

def Krovi_Brun_bitstring_MFPT(n, d):
    """Calculate the MFPT between two bitstrings. n is the bitstring
    length, and d is the Hamming distance between two individuals.
    Formula is given in
    http://math.stackexchange.com/questions/28179/logic-question-ant-walking-a-cube/28188#28188,
    also a variation is given in 'Hitting time for quantum walks on
    the hypercube', Hari Krovi and Todd A. Brun, PHYSICAL REVIEW A 73,
    032341 2006. This is not needed for anything else, just as a check
    that the formula gives same answers as the general MFPT formula
    (see ergodic.py) -- it does."""
    return sum(
        sum(nCk(n, k) for k in range(m+1)) / float(nCk(n-1, m))
        for m in range(n-d, n))

def onemax_fitvals(length):
    return [np.sum(ind) for ind in
            itertools.product(*[(0, 1) for x in range(length)])]

def ga_tm_wrapper(dirname, pmut=None):
    # dirname should be <dir>/ga_length_6, for example
    length = int(dirname.strip("/").split("_")[2])
    tm, hm = generate_ga_tm(length, pmut)
    outfilename = dirname + "/TP.dat"
    np.savetxt(outfilename, tm)
    outfilename = dirname + "/Hamming.dat"
    np.savetxt(outfilename, hm)
        

##
# End of GA (bitstring) stuff
#########################################################    

def simulate_random_walk(f, nsteps, selected, nsaves):
    """f is the transition function. nsteps is the number of steps.
    selected is the set of states (can be a list of integers) in which
    we're interested. nsaves is the max number of samples to save for
    each pair. Return an array of samples for MFPT for each pair (i,
    j) from selected."""

    n = len(selected)
    # samples is all nans to start
    samples = np.nan + np.zeros((n, n, nsaves))
    # in the rw_started matrix, the (i,j)th entry is the time-step at
    # which a walk from i to j began. -1 means we are not currently in
    # a walk from i to j. can't be in a walk from i to j and from j to
    # i simultaneously.
    rw_started = -1 * np.ones((n, n), dtype='int64')
    # for each transition there are nsaves spaces to save samples --
    # this says where to save
    saveidx = np.zeros((n, n), dtype='int')

    def print_state(v, rw_started, samples, t):
        print("%d: %d" % (t, v))

    # su and sv are states (may be integers). u and v are the indices
    # into selected of su and sv
    sv = selected[0]
    for t in range(nsteps):
        # print_state(sv, rw_started, samples, t)

        # when we see a state sv which is of interest
        if sv in selected:
            v = selected.index(sv)

            for u, su in enumerate(selected):

                if rw_started[u,v] == rw_started[v,u] == -1:
                    # never saw u or v before, but this is the
                    # beginning of a walk from v to u
                    rw_started[v,u] = t

                elif rw_started[u,v] > -1:
                    # we are currently in a walk from u to v, and we
                    # have just reached v, so save a sample (now -
                    # start of walk), if there is space
                    if saveidx[u,v] < nsaves:
                        samples[u,v,saveidx[u,v]] = (t - rw_started[u,v])
                        # update the space left
                        saveidx[u,v] += 1
                    # now we start a walk from v to u. because of the
                    # order of these two assignments, this does the
                    # right thing if v == u.
                    rw_started[u,v] = -1
                    rw_started[v,u] = t

                elif rw_started[v,u] > -1:
                    # we are in a walk from v to u, and have
                    # re-encountered v. ignore.
                    pass

                else:
                    raise InternalError

        # transition to a new state
        sv = f(sv)
    return samples

def roulette_wheel(a):
    """Randomly sample an index, weighted by the given sequence of
    probabilities."""
    s = np.sum(a)
    assert s > 0
    r = random.random() * s
    cumsum = 0.0
    for i, v in enumerate(a):
        cumsum += v
        if r < cumsum:
            return i
    raise ValueError("Unexpected: failed to find a slot in roulette wheel")

def random_search(fitvals, steps, allow_repeat=True):
    """Allow replacement, for this particular experiment."""
    if allow_repeat:
        samples = [random.choice(range(len(fitvals))) for i in range(steps)]
    else:
        samples = random.sample(range(len(fitvals)), steps)
    fitness_samples = [fitvals[sample] for sample in samples]
    return samples, fitness_samples, min(fitness_samples)

def hillclimb(tp, fitvals, steps, rw=False):
    s = random.randint(0, len(fitvals)-1)
    samples = []
    fitness_samples = []
    fitval = fitvals[s]
    for i in range(steps):
        t = roulette_wheel(tp[s])
        if rw:
            s = t
            fitval = fitvals[t]
        else:
            # note we are maximising!
            if fitvals[t] > fitval:
                s = t
                fitval = fitvals[t]
        samples.append(s)
        fitness_samples.append(fitval)
    return samples, fitness_samples, fitval

def generate_oz_tm_mfpte(dirname):
    tp = land_of_oz_matrix()
    samples = simulate_random_walk(
        lambda i: roulette_wheel(tp[i]), # transition according to tp
        200, [0, 1, 2], 100)
    mfpte = scipy.stats.nanmean(samples, axis=2)
    mfpte_std = scipy.stats.nanstd(samples, axis=2)
    mfpt = get_mfpt(tp)

    np.savetxt(dirname + "/TP.dat", tp)
    np.savetxt(dirname + "/MFPTE.dat", mfpte)
    np.savetxt(dirname + "/MFPTE_STD.dat", mfpte_std)

def uniformify(tp, p):
    return (tp**p) / (np.sum(tp**p, 1).reshape((len(tp), 1)))

def land_of_oz_matrix():
    """From Kemeny & Snell 1976. The states are rain, nice and
    snow."""
    return np.array([[.5, .25, .25], [.5, .0, .5], [.25, .25, .5]])

def SP_v_MFPT_example_matrices():
    return (np.array([[.1, .5, .4], [.1, .8, .1], [.8, .1, .1]]),
            np.array([[.1, .5, .4], [.1, .8, .1], [.1, .8, .1]]))

def permute_vals(v, k):
    """v is a list of values. We permute by swapping pairs, k times.
    We copy v first, to avoid mutating the original."""
    v = v[:]
    L = len(v)
    for x in range(k):
        i, j = random.randint(0, L-1), random.randint(0, L-1)
        v[i], v[j] = v[j], v[i]
    return v

def mu_sigma(t):
    """Calculate mean(stddev_1(t)) and stddev(stddev_1(t)), ie the
    mean of row stddevs and the stddev of row stddevs."""
    sigma = np.std(t, 1)
    return np.mean(sigma), np.std(sigma)

def gini_coeff(x):
    """A measure of inequality in a distribution. From
    http://www.ellipsix.net/blog/2012/11/the-gini-coefficient-for-distribution-inequality.html"""
    # requires all values in x to be zero or positive numbers,
    # otherwise results are undefined
    n = len(x)
    s = x.sum()
    r = np.argsort(np.argsort(-x)) # calculates zero-based ranks
    return 1 - (2.0 * (r*x).sum() + s)/(n*s)

def detailed_balance(tp, s=None):
    """Calculate whether a given chain has the detailed balance
    condition, that is given a transition matrix tp, with stationary
    state s, that s_i tp_ij = sj tp_ji."""
    if s is None:
        s = get_steady_state(tp)
    # define matrix f (f for flux) by f_ij = s_i tp_ij, and then check
    # if it's symmetric
    f = tp * s.reshape((len(s), 1))
    return is_symmetric(f)
    
###################################################################
# TSP stuff
###################################################################

def two_opt(p):
    """2-opt means choosing any two non-contiguous edges ab and cd,
    chopping them, and then reconnecting (such that the result is
    still a complete tour). There are actually two ways of doing it --
    one is the identity, and one gives a new tour."""
    n = len(p)
    i = random.randint(0, n)
    j = None
    while j == None or abs(i - j) <= 1 or abs(i - j) == n:
        j = random.randint(0, n)
    i, j = min(i, j), max(i, j)
    sol = p[:i+1] + p[j:i:-1] + p[j+1:]
    return canonicalise(sol)

def three_opt(p, broad=False):
    """In the broad sense, 3-opt means choosing any three edges ab, cd
    and ef and chopping them, and then reconnecting (such that the
    result is still a complete tour). There are eight ways of doing
    it. One is the identity, 3 are 2-opt moves (because either ab, cd,
    or ef is reconnected), and 4 are 3-opt moves (in the narrower
    sense)."""
    n = len(p)
    # choose 3 unique edges defined by their first node
    a, c, e = random.sample(range(n+1), 3)
    # without loss of generality, sort
    a, c, e = sorted([a, c, e])
    b, d, f = a+1, c+1, e+1

    if broad == True:
        which = random.randint(0, 7) # allow any of the 8
    else:
        which = random.choice([3, 4, 5, 6]) # allow only strict 3-opt
        
    # in the following slices, the nodes abcdef are referred to by
    # name. x:y:-1 means step backwards. anything like c+1 or d-1
    # refers to c or d, but to include the item itself, we use the +1
    # or -1 in the slice
    if which == 0:
        sol = p[:a+1] + p[b:c+1]    + p[d:e+1]    + p[f:] # identity
    elif which == 1:
        sol = p[:a+1] + p[b:c+1]    + p[e:d-1:-1] + p[f:] # 2-opt
    elif which == 2:
        sol = p[:a+1] + p[c:b-1:-1] + p[d:e+1]    + p[f:] # 2-opt
    elif which == 3:
        sol = p[:a+1] + p[c:b-1:-1] + p[e:d-1:-1] + p[f:] # 3-opt
    elif which == 4:
        sol = p[:a+1] + p[d:e+1]    + p[b:c+1]    + p[f:] # 3-opt
    elif which == 5:
        sol = p[:a+1] + p[d:e+1]    + p[c:b-1:-1] + p[f:] # 3-opt
    elif which == 6:
        sol = p[:a+1] + p[e:d-1:-1] + p[b:c+1]    + p[f:] # 3-opt
    elif which == 7:
        sol = p[:a+1] + p[e:d-1:-1] + p[c:b-1:-1] + p[f:] # 2-opt
        
    return canonicalise(sol)

def canonicalise(p):
    """In any TSP, 01234 is equivalent to 23410. We canonicalise on
    the former. In a symmetric TSP, 01234 is equivalent to 04321. We
    canonicalise on the former. The general recipe is: p[0] is 0, and
    p[1] is the smaller of p[1]'s neighbours (so p[-1] is the
    larger)."""
    assert p[0] == 0
    if p[1] > p[-1]:
        p[1:] = p[-1:0:-1]
    return p


def tsp_tours(n):
    """Generate all tours of length n. A tour is a permutation. But we
    canonicalise as above."""
    for p in itertools.permutations(range(n)):
        if p[0] != 0: continue
        if p[1] > p[-1]: continue
        yield p

def sample_transitions(n, opt=2, nsamples=10000):
    length = len(list(tsp_tours(n)))
    tm = np.zeros((length, length))
    delta = 1.0 / nsamples

    if opt == 3:
        move = three_opt
    else:
        move = two_opt
    
    tours_to_ints = {}
    for i, tour in enumerate(tsp_tours(n)):
        tours_to_ints[tour] = i

    for i, tour in enumerate(tsp_tours(n)):
        for j in range(nsamples):
            t = move(list(tour))
            tm[i][tours_to_ints[tuple(t)]] += delta
    return tm

def kendall_tau_permutation_distance(t1, t2):
    corr, p = scipy.stats.kendalltau(t1, t2)
    return 1.0 - corr

def kendall_tau_permutation_distances(n):
    m = len(list(tsp_tours(n)))
    kt = np.zeros((m, m))
    for i, ti in enumerate(tsp_tours(n)):
        for j, tj in enumerate(tsp_tours(n)):
            kt[i][j] = kendall_tau_permutation_distance(ti, tj)
    return kt

def tsp_tm_wrapper(dirname, opt=2):
    # dirname should be <dir>/tsp_length_6_2_opt, for example
    length = int(dirname.strip("/").split("_")[2])
    tm = sample_transitions(length, opt)
    outfilename = dirname + "/TP.dat"
    np.savetxt(outfilename, tm)
    kt = kendall_tau_permutation_distances(length)
    outfilename = dirname + "/KendallTau.dat"
    np.savetxt(outfilename, kt)

#
# end of TSP stuff
#######################################################

if __name__ == "__main__":
    dirname = sys.argv[1]

    if "depth" in dirname:
        # Matrices have already been generated by Java code.
        pass
    elif "ga" in dirname:
        if "per_ind" in dirname:
            ga_tm_wrapper(dirname)
        else:
            ga_tm_wrapper(dirname, 0.1)
    elif "land_of_oz" in dirname:
        generate_oz_tm_mfpte(dirname)
    elif "tsp" in dirname:
        if "2_opt" in dirname:
            tsp_tm_wrapper(dirname, opt=2)
        elif "3_opt" in dirname:
            tsp_tm_wrapper(dirname, opt=3)
        else:
            raise ValueError("Unexpected dirname " + dirname)
    read_and_get_dtp_mfpt_sp_steps(dirname)
    write_symmetric_remoteness(dirname)
    # estimate_MFPT_with_supernode(dirname)
    # analyse_random_walk(dirname)
    # test_random_walk()
    MSTP_wrapper(dirname)
