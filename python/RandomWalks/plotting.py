#!/usr/bin/env python

import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from sklearn.manifold import MDS
import numpy as np
from matplotlib.ticker import FuncFormatter, MaxNLocator, IndexLocator
import sys
import os
from math import *
import random
import scipy.stats
import scipy.stats.mstats
from random_walks import set_self_transition_zero, map_infinity_to_large, tsp_tours

# MAXTICKS is 1000 in IndexLocator
class MyLocator(mpl.ticker.IndexLocator):
    MAXTICKS=1500

def graph_distance_names(dirname):
    if "depth_6" in dirname:
        return ["D_TP", "MFPT"], ["D$_\mathrm{TP}$", "MFPT"]
    else:
        return [
            "D_TP", "SD_TP",
            "SP", "STEPS",
            "MFPT", "CT",
            "MFPT_VLA", "CT_VLA",
            "CT_amp", "RSP", "FE",
            "D_MSTP_10",
            "D_MSTP_100"
            ], [
            "$D_{\mathrm{TP}}$",
            r"SD$_{\mathrm{TP}}$",
            "SP", "STEPS",
            "MFPT", "CT",
            "MFPTV", "CTV",
            "ACT", "RSP", "FED",
            r"D$_{\mathrm{MSTP}_{10}}$",
            r"D$_{\mathrm{MSTP}_{100}}$"
            ]

def syntactic_distance_names(dirname):
    if "ga_length" in dirname:
        return ["Hamming"]
    elif "tsp_length" in dirname:
        return ["KendallTau"]
    elif "depth" in dirname:
        return [
            # "NodeCount", "MinDepth", "MeanDepth", "MaxDepth",
            # "Symmetry", "MeanFanout", "DiscreteMetric",
            "TED",
            "TAD0", "TAD1", "TAD2", "TAD3", "TAD4", "TAD5",
            "FVD",
            "NCD",
            "OVD",
            "SEMD", # not syntactic of course, but handy to put it here
            ]
    else:
        raise ValueError("Unexpected dirname " + dirname)

def make_grid_plots(dirname, plot_names=None):
    if "depth" in dirname:
        # Assume GP
        if "depth_6" not in dirname:
            ind_names = open(dirname + "/all_trees.dat").read().strip().split("\n")
            ind_names = map(lambda x: x.strip(), ind_names)
        else:
            ind_names = None
    elif "ga_length" in dirname:
        # Assume GA
        length = int(dirname.strip("/").split("_")[2])
        ind_names = [bin(i)[2:] for i in range(2**length)]
    elif "tsp_length" in dirname:
        # Assume TSP
        length = int(dirname.strip("/").split("_")[2])
        if length < 10:
            # 1-digit indices: just concatenate
            ind_names = map(lambda t: ''.join(str(ti) for ti in t),
                            tsp_tours(length))
        else:
            # use original tuple-style string
            ind_names = map(str, tsp_tours(length))

    if plot_names is None:
        syn_names = syntactic_distance_names(dirname)
        grph_names, grph_tex_names = graph_distance_names(dirname)
        plot_names = syn_names + grph_names

    for plot_name in plot_names:
        w = np.genfromtxt(dirname + "/" + plot_name + ".dat")
        if "depth_6" not in dirname:
            assert(len(w) == len(ind_names))
        print plot_name
        make_grid(w, False, dirname + "/" + plot_name)
    print ind_names # better to print them in a list somewhere than in the graph

def make_grid(w, names, filename, colour_map=None, bar=True):
    # we dont rescale the data. matshow() internally scales the data
    # so that the smallest numbers go to black and largest to white.

    # A uniform array will cause a "RuntimeWarning: invalid value
    # encountered in divide" when calculating the colorbar. So ignore
    # that.
    old = np.seterr(invalid='ignore')

    # Can put NaN on the diagonal to avoid plotting it -- makes a bit
    # more space available for other data. But misleading.

    # w += np.diag(np.ones(len(w)) * np.nan)

    # if w contains any NaNs we'll get a misleading result: they won't
    # be plotted, so will appear white, as will the largest finite
    # values of w. So first, replace them with a large value -- 100
    # times the largest finite value.
    map_infinity_to_large(w)

    side = 8.0
    figsize = (side, side)
    fig = plt.figure(figsize=figsize)
    ax = fig.add_subplot(1, 1, 1)
    # consider other colour maps: cm.gray_r for reversed, autumn, hot,
    # gist_earth, copper, ocean, some others, or a custom one for
    # nicer images (not for publication, maybe).
    # im = ax.matshow(w, cmap=cm.gray, interpolation="none")
    if colour_map is None: colour_map = cm.gray
    im = ax.matshow(w, cmap=colour_map, interpolation="nearest")
    if bar:
        fig.colorbar(im, shrink=0.775)

    if names:
        # Turn labels on
        ax.xaxis.set_major_locator(MyLocator(1, 0))
        ax.yaxis.set_major_locator(MyLocator(1, 0))
        ax.set_xticklabels(names, range(len(names)), rotation=90, size=1.0)
        ax.set_yticklabels(names, range(len(names)), size=1.0)
    else:
        # Turn them off
        ax.set_xticklabels([], [])
        ax.set_yticklabels([], [])

    ax.tick_params(length=0, pad=3.0)
    fig.savefig(filename + ".pdf", dpi=300, bbox_inches='tight')
    fig.savefig(filename + ".eps", dpi=300, bbox_inches='tight')
    fig.savefig(filename + ".png", dpi=300, bbox_inches='tight')
    plt.close(fig)
    
    # restore old error settings
    np.seterr(**old)
    

def metric_distortion(a, b):
    """Calculate the metric distortion between two metrics on the same
    space. a and b are samples of the distances between pairs of
    points (can be between all pairs).

    See Gupta's paper on embeddings: given a mapping f: X->Y (both
    metric spaces), the contraction of f is sup(d_X(x, y)/d_Y(f(x),
    f(y))); the expansion of f is sup(d_Y(f(x), f(y))/d_X(x, y)). In
    both cases the value is over all x != y. The distortion is
    contraction * expansion. The best (lowest) possible value is 1. To
    avoid divide-by-zero, this assumes d(x, y) != 0 -- ie x != y, and
    d is strictly positive for distinct elements, which is true of any
    metric and all of our non-metric distance functions also. We just
    overwrite any non-finite values with -1 to exclude the x=y cases.

    In our case, X = Y = the search space, eg trees of depth 2 or
    less. d_X is one metric, eg TED; d_Y is another, eg D_TP; f is the
    identity mapping. This leads to these equations:

    contraction = sup(TED(x, y)/TP(x, y)); expansion = sup(TP(x,
    y)/TED(x, y)).

    Also, it means that the order of arguments (a, b) is
    unimportant."""

    old = np.seterr(divide="ignore", invalid="ignore")
    ab = a/b
    ab[~np.isfinite(ab)] = -1
    contraction = np.max(ab)
    ba = b/a
    ba[~np.isfinite(ba)] = -1
    expansion = np.max(ba)
    distortion = expansion * contraction
    np.seterr(**old)
    return distortion

def metric_distortion_agreement(a, b):
    # because we want a measure of agreement
    return 1.0 / metric_distortion(a, b)

def get_kendall_tau(x, y):
    """Return Kendall's tau, a non-parametric test of association. If
     one of the variables is constant, a FloatingPointError will
     happen and we can just say that there was no association. Note
     this runs Kendall's tau-b, accounting for ties and suitable for
     square tables:
     [http://en.wikipedia.org/wiki/Kendall_tau_rank_correlation_coefficient#Tau-b]
     [http://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kendalltau.html].
     However it is of n^2 time complexity, hence unsuitable for even
     medium-sized inputs."""

    # make sure we raise any error (so we can catch it), don't just
    # splat it on the terminal
    old = np.seterr(all='raise')
    try:
        if (isinstance(x, np.ma.core.MaskedArray) or
            isinstance(y, np.ma.core.MaskedArray)):
            corr, p = scipy.stats.mstats.kendalltau(x, y)
        else:
            corr, p = scipy.stats.kendalltau(x, y)
    except (FloatingPointError, TypeError):
        # TypeError can arise in Kendall tau when both x and y are
        # constant
        corr, p = 0.0, 1.0
    # restore old error settings
    np.seterr(**old)
    return corr, p

def get_spearman_rho(x, y):
    """Return Spearman's rho, a non-parametric test of association. If
     one of the variables is constant, a FloatingPointError will
     happen and we can just say that there was no association.
     [http://en.wikipedia.org/wiki/Spearman's_rank_correlation_coefficient].
     The reason for using this is that the usual Pearson's correlation
     assumes normal distributions, which our distances certainly
     aren't, and Kendall's tau is O(n^2), so unbearably slow."""

    # Make sure we raise any error (so we can catch it), don't just
    # splat it on the terminal. However we will ignore underflow
    # because it seems to happen with every single one. Similar
    # approach here:
    # [https://code.google.com/p/wnd-charm/source/browse/pychrm/trunk/pychrm/FeatureSet.py?r=723]
    old = np.seterr(all='raise', under='ignore')
    try:
        if (isinstance(x, np.ma.core.MaskedArray) or
            isinstance(y, np.ma.core.MaskedArray)):
            corr, p = scipy.stats.mstats.spearmanr(x, y)
        else:
            corr, p = scipy.stats.spearmanr(x, y)
    except FloatingPointError:
        corr, p = 0.0, 1.0
    # restore old error settings
    np.seterr(**old)
    return corr, p

def get_pearson_r(x, y):
    """Return Pearson's R, the most common test of correlation, which
     assumes the variables are each normally distributed. If one of
     the variables is constant, a FloatingPointError will happen and
     we can just say that there was no association."""

    # Make sure we raise any error (so we can catch it), don't just
    # splat it on the terminal.
    old = np.seterr(all='raise')
    try:
        if (isinstance(x, np.ma.core.MaskedArray) or
            isinstance(y, np.ma.core.MaskedArray)):
            corr, p = scipy.stats.mstats.pearsonr(x, y)
        else:
            corr, p = scipy.stats.pearsonr(x, y)
    except FloatingPointError:
        corr, p = 0.0, 1.0
    # restore old error settings
    np.seterr(**old)
    return corr, p

def normalised_rmse(x, y):
    """Normalise x and y to each have unit stddev, then just take a Euclidean distance."""
    x = x / np.std(x)
    y = y / np.std(y)
    return np.sqrt(np.mean((x-y)**2.0))
    
def make_correlation_tables(dirname):

    syn_names = syntactic_distance_names(dirname)
    grph_names, grph_tex_names = graph_distance_names(dirname)

    d = load_data_and_reshape(dirname, syn_names + grph_names, remap_infinity=True)

    def do_line(dist, dist_name):
        line = dist_name.replace("_TP", r"$_{\mathrm{TP}}$")
        for graph_distance in grph_names:
            print(corr_type, "getting association between " + graph_distance + " " + dist)
            if corr_type == "spearmanrho":
                corr, p = get_spearman_rho(d[graph_distance], d[dist])
            elif corr_type == "kendalltau":
                corr, p = get_kendall_tau(d[graph_distance], d[dist])
            elif corr_type == "pearsonr":
                corr, p = get_pearson_r(d[graph_distance], d[dist])
            elif corr_type == "euclidean":
                # there is no p-value associated with this so use 1.0 as placeholder
                corr, p = normalised_rmse(d[graph_distance], d[dist]), 1.0
            elif corr_type == "metric_distortion":
                # there is no p-value associated with this so use 1.0 as placeholder
                corr, p = metric_distortion_agreement(d[graph_distance], d[dist]), 1.0
            else:
                print("Unknown correlation type " + corr_type)
            # Consider stat sig only with spearman, kendall, pearson, only
            # with large depth (not looking at entire space)
            if (corr_type in ["spearmanrho", "kendalltau", "pearsonr"] and
                "depth_6" in dirname):
                if corr > 0.0 and p < 0.05:
                    sig = "*"
                else:
                    sig = " "
                line += r" & {0:1.2f} \hfill {1} ".format(corr, sig)
            else:
                line += r" & {0:1.2f} ".format(corr)
        line += r"\\"
        f.write(line + "\n")

    for corr_type in ["spearmanrho", "pearsonr", "kendalltau",
                      "euclidean", "metric_distortion"]:
        if corr_type == "kendalltau" and len(d["D_TP"]) > 1000:
            print("Omitting Kendall tau because it is infeasible for large matrices")
            continue
        filename = dirname + "/correlation_table_" + corr_type + ".tex"
        f = open(filename, "w")

        if len(grph_names) > 5:
            f.write(r"""\begin{sidewaystable}
""")
            f.write(r"""\small
""")
        else:
            f.write(r"""\begin{table}
""")
        f.write(r"""\centering
\caption{Correlations among distance measures """)
        if corr_type == "spearmanrho":
            f.write("using Spearman's $\rho$: ")
        elif corr_type == "pearsonr":
            f.write("using Pearson's $R$: ")
        elif corr_type == "kendalltau":
            f.write("using Kendall's $\tau$: ")
        elif corr_type == "metric_distortion":
            f.write("using inverse metric distortion: ")
        elif corr_type == "euclidean":
            f.write("using standardised Euclidean distance: ")

        if "depth_1" in dirname:
            f.write("trees of maximum depth 1")
        elif "depth_2" in dirname:
            f.write("trees of maximum depth 2")
        elif "depth_6" in dirname:
            f.write("trees of maximum depth 6")
        elif "length_4_per_ind" in dirname:
            f.write("bitstrings of length 4 (per-individual mutation)")
        elif "length_4" in dirname:
            f.write("bitstrings of length 4 (per-gene mutation)")

        f.write(r"""\label{tab:correlationresults_"""
                + os.path.basename(dirname)
                + "_" + corr_type + "}}\n")
        f.write(r"""\begin{tabular}{""" + "|".join("l" for i in range(1+len(grph_names))) + r"""}
     & """ + " & ".join(grph_tex_names)  + r"""\\
\hline
\hline
""")

        for name, tex_name in zip(grph_names, grph_tex_names):
            do_line(name, tex_name)
        f.write(r"""\hline
\hline
""")
        for syn in syn_names:
            if syn == "SEMD": continue # hack -- we don't want SEMD for now
            do_line(syn, syn)

        f.write(r"""\end{tabular}
""")
        if len(grph_names) > 5:
            f.write(r"""\end{sidewaystable}
""")
        else:
            f.write(r"""\end{table}
""")
        f.close()


def load_data_and_reshape(dirname, names, remap_infinity=False):
    d = {}
    for name in names:
        # print("reading " + name)
        if "estimate_MFPT" in dirname:
            # Use a masked array. Mask missing values...
            m = np.genfromtxt(dirname + "/" + name + ".dat",
                              usemask=True, missing_values="NaN,nan")
            # ... mask the diagonal...
            np.fill_diagonal(m, np.ma.masked)

            # ... and those where mfpte-len < 5...
            filename = dirname + "/MFPTE_len.dat"
            mfpte_len = np.genfromtxt(filename)
            min_vals = 5 # an attempt at reliability
            m[mfpte_len < min_vals] = np.ma.masked

            # FIXME mask those where MFPT < 0.1?
        else:
            m = np.genfromtxt(dirname + "/" + name + ".dat")

        if remap_infinity:
            # substitute an arbitrary large value for any infinities
            map_infinity_to_large(m)

        d[name] = m.reshape(len(m)**2)
    return d

def make_scatter_plots(dirname):
    syn_names = syntactic_distance_names(dirname)
    grph_names, grph_tex_names = graph_distance_names(dirname)
    syn_names = []
    grph_names = ["MFPT", "MFPT_VLA"]
    grph_tex_names = ["MFPT", "MFPTV"]
    
    d = load_data_and_reshape(dirname, syn_names + grph_names)

    # while we have the data loaded in d, make scatter plots

    # graph v graph first
    for name1, tex_name1 in zip(grph_names, grph_tex_names):
        for name2, tex_name2 in zip(grph_names, grph_tex_names):
            if name1 < name2 and name1 == "MFPT" and name2 == "MFPT_VLA": # temp hack
                print "doing MFPT MFPTV"
                # avoid plotting anything against itself, or plotting any pair twice
                make_scatter_plot(dirname, d, name1, tex_name1, name2, tex_name2)

    # graph v syn
    for name1, tex_name1 in zip(syn_names, syn_names):
        for name2, tex_name2 in zip(grph_names, grph_tex_names):
            continue
            make_scatter_plot(dirname, d, name1, tex_name1, name2, tex_name2)

def make_scatter_plot(dirname, d, name1, tex_name1, name2, tex_name2):
    filename = dirname + "/scatter_" + name1 + "_" + name2
    fig = plt.figure(figsize=(5,5))
    ax = fig.add_subplot(1, 1, 1)
    xy = deduplicate_rows(np.array([d[name1], d[name2]]).T)
    x, y = xy.T[0], xy.T[1]
    ax.scatter(x, y)
    ax.set_xlabel(tex_name1)
    ax.set_ylabel(tex_name2)
    fig.savefig(filename + ".eps", bbox_inches='tight')
    fig.savefig(filename + ".pdf", bbox_inches='tight')
    fig.savefig(filename + ".png", bbox_inches='tight')
    plt.close(fig)

def deduplicate_rows(a):
    """From http://stackoverflow.com/questions/14089453/python-remove-duplicates-from-a-multi-dimensional-array"""
    return pd.DataFrame(a).drop_duplicates().values
    
def make_histograms(dirname):
    syn_names = syntactic_distance_names(dirname)
    grph_names, grph_tex_names = graph_distance_names(dirname)

    d = load_data_and_reshape(dirname, syn_names + grph_names)

    # graph and syn names
    for name, tex_name in zip(grph_names + syn_names, grph_tex_names + syn_names):
        make_histogram(dirname, d, name, tex_name)

def make_histogram(dirname, d, name, tex_name):
    if isinstance(d[name], np.ma.core.MaskedArray):
        data = np.ma.compressed(d[name])
    else:
        data = d[name]
    fig = plt.figure(figsize=(4, 3))
    ax = fig.add_subplot(1, 1, 1)
    ax.hist(data, 20, label=tex_name)
    ax.set_yticks([])
    # ax.legend()
    fig.savefig(dirname + "/histogram_" + name + ".pdf")
    fig.savefig(dirname + "/histogram_" + name + ".eps")
    fig.savefig(dirname + "/histogram_" + name + ".png")
    plt.close(fig)

def compare_TP_estimate_v_exact(dirname):

    stp = np.genfromtxt(dirname + "/TP_sampled.dat")
    stp = stp.reshape(len(stp)**2)
    tp = np.genfromtxt(dirname + "/TP.dat")
    tp = tp.reshape(len(tp)**2)

    filename = dirname + "/compare_TP_calculated_v_sampled.tex"
    f = open(filename, "w")
    corr, p = scipy.stats.pearsonr(tp, stp)
    f.write("Pearson R correlation " + str(corr) + "; ")
    f.write("p-value " + str(p) + ". ")
    corr, p = scipy.stats.spearmanr(tp, stp)
    f.write("Spearman rho correlation " + str(corr) + "; ")
    f.write("p-value " + str(p) + ". ")
    if len(stp) < 1000:
        corr, p = scipy.stats.kendalltau(tp, stp)
        f.write("Kendall tau correlation " + str(corr) + "; ")
        f.write("p-value " + str(p) + ". ")
    else:
        f.write("Omitting Kendall tau because it is infeasible for large matrices. ")
    f.close()

def compare_MFPT_estimate_RW_v_exact(dirname):

    def get_indices_of_common_entries(a, b):
        result = []
        for i in b:
            try:
                j = a.index(i)
                result.append(j)
            except ValueError:
                pass
        assert len(result) == len(b)
        return result

    filename = dirname + "/MFPT.dat"
    mfpt = np.genfromtxt(filename)

    filename = dirname + "/compare_MFPT_estimate_RW_v_exact.tex"
    f = open(filename, "w")

    if "depth_2" in dirname:
        lengths = [1298, 12980, 129800]
    elif "depth_1" in dirname:
        # NB with 18, too few values to run correlation
        lengths = [180, 1800, 18000]
    for length in lengths:

        # mfpte: read, mask nan, mask len < 5 (100x100)
        filename = dirname + "/estimate_MFPT_using_RW_" + str(length) + "/MFPT.dat"
        mfpte = np.genfromtxt(filename, usemask=True, missing_values="NaN,nan")
        filename = dirname + "/estimate_MFPT_using_RW_" + str(length) + "/MFPT_len.dat"
        mfpte_len = np.genfromtxt(filename)
        min_vals = 5 # an attempt at reliability
        print("%d of %d values of length < 5" % (np.sum(mfpte_len < min_vals), len(mfpte_len)**2))
        mfpte[mfpte_len < min_vals] = np.ma.masked

        # mfpt: copy, select sampled only to make it 100x100
        mfpt_tmp = mfpt.copy()
        # need to restrict mfpt_tmp to the 100x100 entries which are
        # indicated by the trees_sampled.dat file
        filename = dirname + "/estimate_MFPT_using_RW_" + str(length) + "/trees_sampled.dat"
        trees_sampled = open(filename).read().strip().split("\n")
        filename = dirname + "/all_trees.dat"
        all_trees = open(filename).read().strip().split("\n")
        indices = get_indices_of_common_entries(all_trees, trees_sampled)
        # the selected indices are into both the rows and columns
        mfpt_tmp = mfpt_tmp[indices][:,indices]

        # mfpte will contain the self-hitting time on the diagonal: we
        # want zero there for true comparison.
        set_self_transition_zero(mfpte)

        # reshape both
        mfpte = mfpte.reshape(len(mfpte)**2)
        mfpt_tmp = mfpt_tmp.reshape(len(mfpt_tmp)**2)

        # correlate using mask
        f.write("Number of samples: " + str(length) + "\n")
        corr, p = get_pearson_r(mfpt_tmp, mfpte)
        f.write("Pearson R correlation " + str(corr) + "; ")
        f.write("p-value " + str(p) + ". ")
        corr, p = get_spearman_rho(mfpt_tmp, mfpte)
        f.write("Spearman rho correlation " + str(corr) + "; ")
        f.write("p-value " + str(p) + ". ")
        if len(mfpte) < 1000:
            corr, p = get_kendall_tau(mfpt_tmp, mfpte)
            f.write("Kendall tau correlation " + str(corr) + "; ")
            f.write("p-value " + str(p) + ". ")
        else:
            f.write("Omitting Kendall tau because it is infeasible for large matrices. ")
        f.write("\n")
    f.close()

def write_steady_state(dirname):
    """Get steady state, write it out and plot it. Also calculate the
    in-degree of each node, by summing columns. Plot that on the same
    plot. Calculate the correlation between steady-state and
    in-degree. Calculate the stddev of the steady-state as well, and
    (why not) the stddev of the TP matrix as well."""
    from random_walks import get_steady_state
    tp = np.genfromtxt(dirname + "/TP.dat")
    ss = get_steady_state(tp)
    s = ("Stddev " + str(np.std(ss)) + ". ")
    open(dirname + "/steady_state.tex", "w").write(s)
    s = ("Stddev " + str(np.std(tp)) + ". ")
    open(dirname + "/tp_stddev.tex", "w").write(s)
    cs = np.sum(tp, axis=0)
    cs /= np.sum(cs)
    s = ("Pearson correlation between steady-state vector "
         + "and normalised in-degree vector"
         + str(scipy.stats.pearsonr(ss, cs)) + ". ")
    open(dirname + "/in_degree.tex", "w").write(s)

    fig = plt.figure(figsize=(5.0, 2.5))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_yscale('log')
    offset = int(log(len(ss), 2)) + 1
    ax.set_xlim((-offset, len(ss)-1+offset))
    plt.ylabel("Log-probability")
    ax.plot(ss, label="Stationary state", lw=1.5, color=(0, 0, 0))
    ax.set_xticklabels([], [])
    if ("depth_1" in dirname) or ("ga_length" in dirname):
        plt.legend(loc=3)
    else:
        plt.legend(loc=1)
    # filename = dirname + "/steady_state.dat"
    # np.savetxt(filename, ss)
    # filename = dirname + "/in_degree.dat"
    # np.savetxt(filename, cs)
    filename = dirname + "/steady_state_alone"
    fig.savefig(filename + ".pdf")
    fig.savefig(filename + ".eps")
    plt.close(fig)

    fig = plt.figure(figsize=(5.0, 2.5))
    ax = fig.add_subplot(1, 1, 1)
    ax.set_yscale('log')
    offset = int(log(len(ss), 2)) + 1
    ax.set_xlim((-offset, len(ss)-1+offset))
    plt.ylabel("Log-probability")
    ax.plot(cs, label="Normalised in-degree", lw=1.5, color=(0, 0, 0))
    ax.set_xticklabels([], [])
    if ("depth_1" in dirname) or ("ga_length" in dirname):
        plt.legend(loc=3)
    else:
        plt.legend(loc=1)
    filename = dirname + "/normalised_in_degree_alone"
    fig.savefig(filename + ".pdf")
    fig.savefig(filename + ".eps")
    plt.close(fig)

    s = ("Detailed balance check: " + str(random_walks.detailed_balance(tp, ss)))
    open(dirname + "/detailed_balance.tex", "w").write(s)

def make_mds_images(dirname, names=None):
    """Make MDS images for multiple distance matrices. Each matrix
    must be symmetric. Must not contain any infinities, which prevents
    SD_TP in a space like ga_length_4_per_ind."""

    if "depth" in dirname:
        if names is None:
            names = ["CT", "SD_TP", "FE", "TED", "TAD0", "TAD2", "OVD", "FVD"]
            names = ["CT_amp", "RSP", "TAD1"]
        # read in the trees
        filename = dirname + "/all_trees.dat"
        # labels = open(filename).read().strip().split("\n")
        labels = None
    elif "ga_length" in dirname:
        if names is None:
            names = ["CT", "SD_TP", "FE", "Hamming"]
        labels = None
    elif "tsp_length" in dirname:
        if names is None:
            names = ["CT", "SD_TP", "FE", "KendallTau"]
        labels = None
    for name in names:
        m = np.genfromtxt(dirname + "/" + name + ".dat")
        make_mds_image(m, dirname + "/" + name + "_MDS", labels)

def make_mds_image(m, filename, labels=None, colour=None):
    """Given a matrix of distances, project into 2D space using
    multi-dimensional scaling and produce an image."""

    mds_data_filename = filename + ".dat"

    try:
        # if we've previously computed, load it
        p = np.genfromtxt(mds_data_filename)
    except:
        # else, compute it now (and save)
        
        # Construct MDS object with various defaults including 2d
        mds = MDS(dissimilarity="precomputed")
        # Fit
        try:
            f = mds.fit(m)
        except ValueError as e:
            print("Can't run MDS for " + filename + ": " + str(e))
            return

        # Get the embedding in 2d space
        p = f.embedding_

        # save
        np.savetxt(mds_data_filename, p)

    # Make an image
    fig, ax = plt.subplots(figsize=(5, 5))
    # x- and y-coordinates
    ax.set_aspect('equal')

    ax.scatter(p[:,0], p[:,1], edgecolors='none')

    if labels != None:
        print filename
        # hard-coded for GP depth-2
        indices = [0, 2, 50, 52]
        for i in indices:
            print labels[i], p[i,0], p[i,1]
            # can print some labels directly on the graph as follows,
            # but maybe it's better done manually, after printing
            # their locations to terminal?

            # plt.text(p[i,0], p[i,1], labels[i], style='italic',
            #         bbox={'facecolor':'red', 'alpha':0.5, 'pad':10})

    fig.savefig(filename + ".pdf")
    fig.savefig(filename + ".eps")
    fig.savefig(filename + ".png")
    plt.close(fig)

    # Could use custom marker types and colours to get an interesting
    # diagram?
    # http://matplotlib.org/api/path_api.html#matplotlib.path.Path
    # (pass marker=Path() from above), and then use random colours?

def new_ocean():
    # make a new ocean-derived colourmap
    oceancmap = cm.get_cmap("ocean", 5) # generate an ocean map with 5 values 
    ocean_vals = oceancmap(np.arange(5)) # extract those values as an array 
    ocean_vals = ocean_vals[1:] # discard the green bits at the bottom of the ocean
    new_ocean = mpl.colors.LinearSegmentedColormap.from_list("newocean", ocean_vals) 
    return new_ocean

def make_UCD_research_images():
    dirname = "../../results/depth_2/"
    tree_names = open("../../results/depth_2/all_trees.dat").read().strip().split("\n")

    # names = ["TED", "OVD", "CT", "FVD", "FE", "SD_TP", "TAD0", "TAD2"]
    names = ["OVD", "FE", "SD_TP", "TED"]
    names = []
    
    # choose a colour scheme
    colour_maps = [new_ocean(), cm.summer, cm.autumn, cm.copper]

    def colour_val(tree_name):
        return max(1.0, random.random() * 0.25 + len(tree_name) / 19.0)
    def marker_size():
        return 30 + random.random() * 20

    for name, colour_map in zip(names, colour_maps):
        # do mds
        mds_data_filename = dirname + "/" + name + "_MDS.dat"
        mds_output_filename = dirname + "/UCD_research_images/" + name + "_MDS"
        p = np.genfromtxt(mds_data_filename)
        # Make an image
        fig, ax = plt.subplots(figsize=(5, 5), frameon=False)
        ax.axis('off')
        # x- and y-coordinates
        ax.set_aspect('equal')
        colour_vals = [colour_val(tree_name) for tree_name in tree_names]
        marker_sizes = [marker_size() for tree_name in tree_names]
        marker = '^'
        ax.scatter(p[:,0], p[:,1], s=marker_sizes,
                   marker=marker, c=colour_vals, cmap=colour_map,
                   alpha=0.5, edgecolors='none')
        
        mnx, mxx = min(p[:,0]), max(p[:,0])
        mny, mxy = min(p[:,1]), max(p[:,1])
        rngx = (mxx - mnx)
        rngy = (mxy - mny)
        margin = 0.03
        ax.set_xlim((mnx - margin * rngx, mxx + margin * rngx))
        ax.set_ylim((mny - margin * rngy, mxy + margin * rngy))
        #plt.axis('off')
        
        fig.savefig(mds_output_filename + ".png", bbox_inches='tight')
        fig.savefig(mds_output_filename + ".pdf", bbox_inches='tight')

    names = ["OVD", "FE", "SD_TP", "TED"]
    colour_maps = [new_ocean(), cm.summer, cm.YlOrRd, cm.copper]

    for name, colour_map in zip(names, colour_maps):
        # do grid
        grid_data_filename = dirname + "/" + name + ".dat"
        grid_output_filename = dirname + "/UCD_research_images/" + name + "_grid"
        p = np.genfromtxt(grid_data_filename)
        make_grid(p, None, grid_output_filename, colour_map, bar=False)

def make_SIGEvo_images():
    gp_dirname = "../../results/depth_2/"
    ga_dirname = "../../results/ga_length_10_per_ind/"
    tsp_dirname = "../../results/tsp_length_7_2_opt/"

    def clamp(x):
        return max(0.0, min(1.0, x))
    def colour_val(i):
        return clamp(np.log(fit_vals[i]) / 5.5) # NB hardcoded for our fit vals
    def marker_size(tree_name):
        return 20 + 50 * tree_len(tree_name) / 7.0
    def tree_len(tree_name):
        return sum(tree_name.count(s) for s in "+-*/xy")
    def count_ones(i):
        # count ones in the binary rep
        return bin(i).count("1")
    def tsp_fit(t):
        def d(a, b): return sqrt((a[0]-b[0])**2.0 + (a[1]-b[1])**2.0)
        # place a few arbitrary cities
        c = [[0, 0],
             [10, 1],
             [5, 5],
             [2, 8],
             [8, 9],
             [5, 9],
             [7, 1]
        ]
        s = t + (t[0],) # replicate initial city to make it easy
        return sum(d(c[s[i]], c[s[i+1]]) for i in range(len(t)))
        
    
    names = ["OVD", "FE", "SD_TP", "TED", "TAD1", "FVD", "CT", "SEMD", "Hamming", "SEMD_alternate_target", "KendallTau"]
    colour_maps = [new_ocean(), cm.PuRd_r, cm.YlOrRd, cm.copper, cm.autumn, cm.Purples_r, cm.YlGnBu_r, cm.summer, cm.BuGn_r, cm.afmhot, cm.BuPu_r]

    for name, colour_map in zip(names, colour_maps):

        # a hack for doing just a few quickly
        if name not in ["SEMD_alternate_target", "KendallTau"]: continue
        
        if name == "Hamming":
            # GA
            mds_data_filename = ga_dirname + "/" + name + "_MDS.dat"
            mds_output_filename = ga_dirname + "/SIGEvo_images/" + name + "_MDS"
            colour_vals = [count_ones(i) for i in range(2**10)]
            marker_sizes = [30 for i in range(2**10)]
            marker = 's' # square

        elif name == "KendallTau":
            # TSP
            mds_data_filename = tsp_dirname + "/" + name + "_MDS.dat"
            mds_output_filename = tsp_dirname + "/SIGEvo_images/" + name + "_MDS"
            colour_vals = [tsp_fit(t) for t in tsp_tours(7)] # will be scaled
            marker_sizes = [30 for i in range(len(colour_vals))]
            marker = 'o' # circle

        else:
            # GP
            tree_names = open("../../results/depth_2/all_trees.dat").read().strip().split("\n")

            if name == "SEMD_alternate_target":
                fit_vals = np.genfromtxt("../../results/depth_2/all_trees_fitness_alternate_target.dat")
            else:
                fit_vals = np.genfromtxt("../../results/depth_2/all_trees_fitness.dat")
            mds_data_filename = gp_dirname + "/SEMD_MDS.dat" # not SEMD_alternate_target -- no need
            mds_output_filename = gp_dirname + "/SIGEvo_images/" + name + "_MDS"
            colour_vals = [colour_val(i) for i in range(len(tree_names))]
            marker_sizes = [marker_size(tree_name) for tree_name in tree_names]
            marker = '^' # triangle


        # get existing MDS data
        p = np.genfromtxt(mds_data_filename)
        
        # Make an image
        fig, ax = plt.subplots(figsize=(5, 5), frameon=True)
        ax.axis('on')
        # x- and y-coordinates
        ax.set_aspect('equal')
        ax.scatter(p[:,0], p[:,1], s=marker_sizes,
                   marker=marker, c=colour_vals, cmap=colour_map,
                   alpha=0.5, edgecolors='none')
        
        fig.savefig(mds_output_filename + ".png", bbox_inches='tight')
        fig.savefig(mds_output_filename + ".pdf", bbox_inches='tight')


if __name__ == "__main__":
    cmd = sys.argv[1]
    dirname = sys.argv[2]

    if cmd == "compareTPEstimateVExact":
        compare_TP_estimate_v_exact(dirname)
    elif cmd == "compareMFPTEstimateRWVExact":
        compare_MFPT_estimate_RW_v_exact(dirname)
    elif cmd == "makeCorrelationTable":
        make_correlation_tables(dirname)
    elif cmd == "makeGridPlots":
        make_grid_plots(dirname)
    elif cmd == "makeGridPlotsByName":
        make_grid_plots(dirname, sys.argv[3:])
    elif cmd == "writeSteadyState":
        write_steady_state(dirname)
    elif cmd == "makeMDSImages":
        make_mds_images(dirname)
    elif cmd == "makeMDSImagesByName":
        make_mds_images(dirname, sys.argv[3:])
    elif cmd == "makeScatterPlots":
        make_scatter_plots(dirname)
    elif cmd == "makeHistograms":
        make_histograms(dirname)
    elif cmd == "makeUCDResearchImages":
        make_UCD_research_images()
    elif cmd == "makeSIGEvoImages":
        make_SIGEvo_images()
