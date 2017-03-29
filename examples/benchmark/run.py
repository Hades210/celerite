#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import division, print_function

import os
import sys
import argparse
import numpy as np
import numpy.__config__ as npconf

import celerite
from celerite import terms
from celerite.timer import benchmark
from celerite.solver import (
    lapack_variant, Solver, SparseSolver, CholeskySolver
)

parser = argparse.ArgumentParser()
parser.add_argument("--lapack", action="store_true")
parser.add_argument("--cholesky", action="store_true")
parser.add_argument("--default", action="store_true")
parser.add_argument("--sparse", action="store_true")
parser.add_argument("--george", action="store_true")
parser.add_argument("--minnpow", type=int, default=6)
parser.add_argument("--maxnpow", type=int, default=19)
parser.add_argument("--minjpow", type=int, default=0)
parser.add_argument("--maxjpow", type=int, default=8)
parser.add_argument("--outdir",
                    default=os.path.dirname(os.path.abspath(__file__)))
args = parser.parse_args()

if args.george:
    try:
        import george
        from george.kernels import CeleriteKernel
    except ImportError:
        print("To run the george benchmark, you must install the dev version "
              "of george with the 'CeleriteKernel' included")
        raise

# BLAS info
blas_opt_info = npconf.get_info("blas_opt_info")

# The dimension of the problem
N = 2**np.arange(args.minnpow, args.maxnpow + 1)
J = 2**np.arange(args.minjpow, args.maxjpow + 1)

header = ""
for k in ["lapack", "cholesky", "sparse", "default", "george",
          "minnpow", "maxnpow", "minjpow", "maxjpow"]:
    header += "# {0}: {1}\n".format(k, getattr(args, k))
header += "# platform: {0}\n".format(sys.platform)
header += "# with_lapack: {0}\n".format(celerite.__with_lapack__)
header += "# lapack_variant: {0}\n".format(lapack_variant())
header += "# N: {0}\n".format(list(N))
header += "# J: {0}\n".format(list(J))
header += "xi,yi,j,n,comp_time,ll_time\n"

fn = "benchmark_{0}".format(sys.platform)
if args.default:
    fn += "_default"
elif args.cholesky:
    fn += "_cholesky"
elif args.sparse:
    fn += "_sparse"
elif args.lapack:
    fn += "_lapack"
elif args.george:
    fn += "_george"
fn += ".csv"
fn = os.path.join(args.outdir, fn)
print("filename: {0}".format(fn))
with open(fn, "w") as f:
    f.write(header)
print(header, end="")

# Simulate a "dataset"
np.random.seed(42)
t = np.sort(np.random.rand(np.max(N)))
yerr = np.random.uniform(0.1, 0.2, len(t))
y = np.sin(t)

for xi, j in enumerate(J):
    kernel = terms.RealTerm(1.0, 0.1)
    for k in range((2*j - 1) % 2):
        kernel += terms.RealTerm(1.0, 0.1)
    for k in range((2*j - 1) // 2):
        kernel += terms.ComplexTerm(0.1, 2.0, 1.6)
    coeffs = kernel.coefficients
    assert 2*j == len(coeffs[0]) + 2*len(coeffs[2]), "Wrong number of terms"

    if args.george:
        george_kernel = None
        for a, c in zip(*(coeffs[:2])):
            k = CeleriteKernel(a=a, b=0.0, c=c, d=0.0)
            george_kernel = k if george_kernel is None else george_kernel + k
        for a, b, c, d in zip(*(coeffs[2:])):
            k = CeleriteKernel(a=a, b=0.0, c=c, d=0.0)
            george_kernel = k if george_kernel is None else george_kernel + k
        solver = george.GP(george_kernel, solver=george.HODLRSolver)
    elif args.cholesky:
        solver = CholeskySolver()
    elif args.sparse:
        solver = SparseSolver()
    else:
        use_lapack = bool(args.lapack if not args.default else j >= 4)
        solver = Solver(use_lapack)

    for yi, n in enumerate(N):
        if args.george:
            params = [t[:n], yerr[:n]]
            comp_time = benchmark("solver.compute(*params)",
                                  "from __main__ import solver, params")
            solver.compute(*params)
            y0 = y[:n]
            ll_time = benchmark("solver.lnlikelihood(y0)",
                                "from __main__ import solver, y0")
        else:
            params = list(coeffs)
            params += [t[:n], yerr[:n]**2]
            comp_time = benchmark("solver.compute(*params)",
                                  "from __main__ import solver, params")
            solver.compute(*params)
            y0 = y[:n]
            ll_time = benchmark("solver.dot_solve(y0)",
                                "from __main__ import solver, y0")
        msg = "{0},{1},{2},{3},{4:e},{5:e}\n".format(xi, yi, j, n, comp_time,
                                                     ll_time)
        with open(fn, "a") as f:
            f.write(msg)
        print(msg, end="")

        if comp_time + ll_time >= 5:
            break
