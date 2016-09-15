import csv
import json
import os

import numexpr as ne
import numpy as np

from ...constants import AB_OFFSET, FOUR_PI, MAG_FAC, MPC_CGS
from ..module import Module

CLASS_NAME = 'Filter'


class Filter(Module):
    """Band-pass filter.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        bands = kwargs.get('bands', '')
        systems = kwargs.get('systems', '')
        instruments = kwargs.get('instruments', '')
        bands = [bands] if isinstance(bands, str) else bands

        self._bands = []
        self._systems = []
        self._instruments = []
        self._paths = []
        with open(
                os.path.join('friendlyfit', 'modules', 'observables',
                             'filterrules.json')) as f:
            filterrules = json.loads(f.read())
            for bi, band in enumerate(bands):
                for rule in filterrules:
                    if systems[bi] not in filterrules[rule].get("systems", []):
                        continue
                    if (instruments[bi] not in filterrules[rule].get(
                            "instruments", [])):
                        continue
                    for bnd in enumerate(rule.get('filters', [])):
                        if band == bnd or band == '':
                            self._bands.append(bnd)
                            self._band_offsets.append(rule['filters'][bnd].get(
                                'AB-Vega', 0.0))
                            self._paths.append(rule['filters'][bnd]['path'])

        self._band_names = list(set(self._bands))
        self._n_bands = len(self._band_names)
        self._band_wavelengths = [[] for i in range(self._n_bands)]
        self._transmissions = [[] for i in range(self._n_bands)]
        self._min_waves = [0.0] * self._n_bands
        self._max_waves = [0.0] * self._n_bands
        self._filter_integrals = [0.0] * self._n_bands

        for i, path in enumerate(self._paths):
            with open(
                    os.path.join('friendlyfit', 'modules', 'observables',
                                 'filters', path), 'r') as f:
                rows = []
                for row in csv.reader(f, delimiter=' ', skipinitialspace=True):
                    rows.append([float(x) for x in row[:2]])
            self._band_wavelengths[i], self._transmissions[i] = list(
                map(list, zip(*rows)))
            self._min_waves[i] = min(self._band_wavelengths[i])
            self._max_waves[i] = max(self._band_wavelengths[i])
            self._filter_integrals[i] = np.trapz(
                np.array(self._transmissions[i]),
                np.array(self._band_wavelengths[i]))

    def process(self, **kwargs):
        self._dist_const = np.log10(FOUR_PI * (kwargs['lumdist'] * MPC_CGS)**2)
        self._luminosities = kwargs['luminosities']
        self._bands = kwargs['bands']
        eff_fluxes = []
        for li, band in enumerate(self._luminosities):
            cur_band = self._bands[li]
            bi = self._band_names.index(cur_band)
            sed = kwargs['seds'][li]
            wavs = kwargs['bandwavelengths'][bi]
            dx = wavs[1] - wavs[0]
            itrans = np.interp(wavs, self._band_wavelengths[bi],
                               self._transmissions[bi])
            # if li == 0:
            #     ef = ne.evaluate('sum(itrans * sed)')
            # else:
            #     ef = ne.re_evaluate()
            # eff_fluxes.append(dx * ef)
            yvals = [x * y for x, y in zip(itrans, sed)]
            eff_fluxes.append(
                np.trapz(
                    yvals, dx=dx) / self._filter_integrals[bi])
        mags = self.abmag(eff_fluxes)
        return {'model_magnitudes': mags}

    def band_names(self):
        return self._band_names

    def abmag(self, eff_fluxes):
        return [(np.inf if x == 0.0 else
                 (AB_OFFSET - MAG_FAC * (np.log10(x) - self._dist_const)))
                for x in eff_fluxes]

    def request(self, request):
        if request == 'bandnames':
            return self._band_names
        elif request == 'bandwavelengths':
            return list(map(list, zip(*[self._min_waves, self._max_waves])))
        return []
