#!/usr/bin/env python
import numpy as np
from numpy.polynomial import Polynomial
import os.path as path
import pathlib
import scipy.signal as signal
from typing import List


def load_grid(root_path):
    """ Loads rho-grid. """
    grid_path = path.join(root_path, 'rho_info.txt')
    grid = np.loadtxt(grid_path, skiprows=1, usecols=[0])
    return grid


def interpolate_energies_2d(grid, energies):
    """ Fits a parabola to given energies and returns its extremum point (barrier). """
    parabola_coefs = Polynomial.fit(grid, energies, 2).convert().coef
    barrier_position = -parabola_coefs[1] / 2 / parabola_coefs[2]
    return barrier_position


def find_barrier(root_path, J, K, sym, grid):
    """ Reads 2d energies for given arguments, finds the peak in the ground energy pathway and interpolates barrier position. """
    energies_path = path.join(root_path, f'J_{J}', f'K_{K}', f'symmetry_{sym}', 'basis', 'energies_2d.fwc')
    if path.exists(energies_path):
        energies = np.loadtxt(energies_path, skiprows=1, usecols=[0])
        peaks = signal.find_peaks(energies, height=(-5000, 5000))[0]
        barrier = interpolate_energies_2d(grid[peaks[0] - 1 : peaks[0] + 2], energies[peaks[0] - 1 : peaks[0] + 2])
        return barrier
    return 0


def select_interpolating_Js(J: int) -> List[int]:
    """ Selects the values of *J_low* and *J_high* used to interpolate a given *J*. """
    if J <= 8:
        return [4, 8]
    elif J >= 52:
        return [52, 56]
    else:
        J_low = int(J / 4) * 4
        J_high = J_low + 4
        return [J_low, J_high]


def select_interpolating_Ks(J: int, K: int) -> List[int]:
    """ Selects the values of *K_low* and *K_high* used to interpolate a given *K*. """
    step_K = 2
    max_K = min(int(J / step_K), 20)
    if K >= max_K - step_K:
        return [max(max_K - step_K, 0), max_K]
    else:
        K_low = int(K / step_K) * step_K
        K_high = K_low + step_K
        return [K_low, K_high]


def get_symmetry_letter(sym_code: int):
    """ Returns symmetry letter associated with the given *sym_code* of wave functions. """
    if sym_code == 0:
        return 'S'
    elif sym_code == 1:
        return 'A'
    else:
        raise Exception('Wrong symmetry code')


def get_channels_file_path(molecule: str, J: int, K: int, sym: int) -> str:
    """ Generates path to the channels file corresponding to given *molecule*, *J*, *K*, and *symmetry*. """
    script_folder_path = pathlib.Path(__file__).resolve().parent
    molecule_folder = molecule + '_full'
    J_folder = 'J{:02}'.format(J)
    symmetry_letter = get_symmetry_letter(sym)
    K_folder = 'K{:02}'.format(K) + symmetry_letter
    return script_folder_path / 'script_data' / molecule_folder / J_folder / K_folder / 'channels.dat'


def load_lowest_barrier_info(channels_file_path: str) -> List[float]:
    """ Loads positions and energies of lowest barrier tops in channels A, B and S from the specified channels file. """
    with open(channels_file_path) as channels_file:
        channel_lines = channels_file.readlines()
    barrier_positions = [0]*3
    for line in channel_lines:
        line_tokens = line.split()
        group_ind = int(line_tokens[1]) - 1
        barrier_position = float(line_tokens[2])
        if barrier_positions[group_ind] == 0:
            barrier_positions[group_ind] = barrier_position
        if all(position > 0 for position in barrier_positions):
            break
    return barrier_positions


def linear_interpolation_1d(point1: List[float], point2: List[float], query_x: float) -> float:
    """ Uses 2 (x, y) points to linearly interpolate the value at *query_x*. """
    return (point2[1] - point1[1]) / (point2[0] - point1[0]) * (query_x - point1[0]) + point1[1]


def linear_interpolation_2d(point1: List[float], point2: List[float], point3: List[float], query_point: List[float]) -> float:
    """ Uses 3 (x, y, z) points to linearly interpolate the value at *query_point* (x, y). """
    # Interpolates in each dimension separately and add up the results
    interp1 = linear_interpolation_1d([point1[i] for i in [0, 2]], [point2[i] for i in [0, 2]], query_point[0])
    interp2 = linear_interpolation_1d(point1[1:], point3[1:], query_point[1])
    return interp1 + interp2 - point1[2]


def interpolate_barrier_positions_JK(molecule: str, J: int, K: int, symmetry: int) -> List[float]:
    """ Interpolates known barrier positions to estimate positions for given arguments. """
    Js_interp = select_interpolating_Js(J)
    Ks_interp = select_interpolating_Ks(Js_interp[0], K)

    # Load known barrier positions for interpolation
    barrier_positions_known = [[0]*len(Ks_interp) for i in range(len(Js_interp))]
    for i in range(len(Js_interp)):
        for j in range(len(Ks_interp)):
            channels_file_path = get_channels_file_path(molecule, Js_interp[i], Ks_interp[j], symmetry)
            lowest_barriers = load_lowest_barrier_info(channels_file_path)
            barrier_positions_known[i][j] = lowest_barriers

    # Interpolate barrier positions (B, A, S)
    barrier_positions = [0]*len(barrier_positions_known[0][0])
    for i in range(len(barrier_positions_known[0][0])):
        point1 = [Js_interp[0], Ks_interp[0], barrier_positions_known[0][0][i]]
        point2 = [Js_interp[1], Ks_interp[0], barrier_positions_known[1][0][i]]
        point3 = [Js_interp[0], Ks_interp[1], barrier_positions_known[0][1][i]]
        barrier_positions[i] = linear_interpolation_2d(point1, point2, point3, [J, K])

    return barrier_positions


def get_pathway_index(pathway_letter: str) -> int:
    """ Returns pathway index. """
    if pathway_letter == 'B':
        return 0
    elif pathway_letter == 'A':
        return 1
    elif pathway_letter == 'S':
        return 2
    else:
        raise Exception('Unknown pathway')


def main():
    root_path = '/global/cfs/cdirs/m409/gaidai/ozone/dev/666'
    molecule = '868'
    sym = 0
    pathway = 'S'
    Js = list(range(0, 33, 2)) + list(range(36, 65, 4))
    Ks = list(range(0, 21, 2))

    barriers = np.zeros((len(Ks), len(Js)))
    grid = load_grid(root_path)
    for J_ind in range(len(Js)):
        J = Js[J_ind]
        for K_ind in range(len(Ks)):
            K = Ks[K_ind]
            if K > J:
                continue
            elif molecule == '666':
                barriers[K_ind, J_ind] = find_barrier(root_path, J, K, sym, grid)
            else:
                # Assuming the only symmetries in this case are 0 or 1
                K_sym = sym if K % 2 == 0 else 1 - sym
                barrier_positions = interpolate_barrier_positions_JK(molecule, J, K, K_sym)
                barriers[K_ind, J_ind] = barrier_positions[get_pathway_index(pathway)]

    np.savetxt(path.join('script_data', 'barriers', molecule, f'sym_{sym}', pathway, 'barriers.txt'), barriers)


if __name__ == '__main__':
    main()
