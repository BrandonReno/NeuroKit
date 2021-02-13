# -*- coding: utf-8 -*-
from warnings import warn

import numpy as np
import pandas as pd
import scipy.linalg

# from ..ecg import ecg_rsp # TODO: why is ecg_rsp imported as a module, not a function?
from ..ecg.ecg_rsp import ecg_rsp
from ..misc import NeuroKitWarning
from ..rsp import rsp_process
from ..signal import signal_filter, signal_interpolate, signal_rate, signal_resample, signal_timefrequency
from ..signal.signal_formatpeaks import _signal_formatpeaks_sanitize
from .hrv_utils import _hrv_get_rri


def hrv_rsa(
    ecg_signals, rsp_signals=None, rpeaks=None, sampling_rate=1000, continuous=False, window=None, window_number=None
):
    """Respiratory Sinus Arrhythmia (RSA)

    Respiratory sinus arrhythmia (RSA), also referred to as 'cardiac coherence' or 'physiological
    coherence' (though these terms are often encompassing a wider meaning), is the naturally occurring
    variation in heart rate during the breathing cycle. Metrics to quantify it are often used as a
    measure of parasympathetic nervous system activity. Neurophysiology informs us that the functional
    output of the myelinated vagus originating from the nucleus ambiguus has a respiratory rhythm.
    Thus, there would a temporal relation between the respiratory rhythm being expressed in the firing
    of these efferent pathways and the functional effect on the heart rate rhythm manifested as RSA.
    Importantly, several methods exist to quantify RSA:

    - The *Peak-to-trough (P2T)* algorithm measures the statistical range in milliseconds of the heart
    period oscillation associated with synchronous respiration. Operationally, subtracting the shortest
    heart period during inspiration from the longest heart period during a breath cycle produces an estimate
    of RSA during each breath. The peak-to-trough method makes no statistical assumption or correction
    (e.g., adaptive filtering) regarding other sources of variance in the heart period time series that
    may confound, distort, or interact with the metric such as slower periodicities and baseline trend.
    Although it has been proposed that the P2T method "acts as a time-domain filter dynamically centered
    at the exact ongoing respiratory frequency" (Grossman, 1992), the method does not transform the time
    series in any way, as a filtering process would. Instead the method uses knowledge of the ongoing
    respiratory cycle to associate segments of the heart period time series with either inhalation or
    exhalation (Lewis, 2012).

    - The *Porges-Bohrer (PB)* algorithm assumes that heart period time series reflect the sum of several
    component time series. Each of these component time series may be mediated by different neural
    mechanisms and may have different statistical features. The Porges-Bohrer method applies an algorithm
    that selectively extracts RSA, even when the periodic process representing RSA is superimposed on a
    complex baseline that may include aperiodic and slow periodic processes. Since the method is designed
    to remove sources of variance in the heart period time series other than the variance within the
    frequency band of spontaneous breathing, the method is capable of accurately quantifying RSA when
    the signal to noise ratio is low.

    Parameters
    ----------
    ecg_signals : DataFrame
        DataFrame obtained from `ecg_process()`. Should contain columns `ECG_Rate` and `ECG_R_Peaks`.
        Can also take a DataFrame comprising of both ECG and RSP signals, generated by `bio_process()`.
    rsp_signals : DataFrame
        DataFrame obtained from `rsp_process()`. Should contain columns `RSP_Phase` and `RSP_PhaseCompletion`.
        No impact when a DataFrame comprising of both the ECG and RSP signals are passed as `ecg_signals`.
        Defaults to None.
    rpeaks : dict
        The samples at which the R-peaks of the ECG signal occur. Dict returned by `ecg_peaks()`,
        `ecg_process()`, or `bio_process()`. Defaults to None.
    sampling_rate : int
        The sampling frequency of signals (in Hz, i.e., samples/second).
    continuous : bool
        If False, will return RSA properties computed from the data (one value per index).
        If True, will return continuous estimations of RSA of the same length as the signal.
        See below for more details.
    window : int
        For calculating RSA second by second. Length of each segment in seconds. If None (default),
        window will be set at 32 seconds.
    window_number : int
        Between 2 and 8. For caculating RSA second by second. Number of windows to be calculated in
        Peak Matched Multiple Window. If None (default), window_number will be set at 8.

    Returns
    ----------
    rsa : dict
        A dictionary containing the RSA features, which includes:

        - "*RSA_P2T_Values*": the estimate of RSA during each breath cycle, produced by subtracting
          the shortest heart period (or RR interval) from the longest heart period in ms.

        - "*RSA_P2T_Mean*": the mean peak-to-trough across all cycles in ms

        - "*RSA_P2T_Mean_log*": the logarithm of the mean of RSA estimates.

        - "*RSA_P2T_SD*": the standard deviation of all RSA estimates.

        - "*RSA_P2T_NoRSA*": the number of breath cycles
          from which RSA could not be calculated.

        - "*RSA_PorgesBohrer*": the Porges-Bohrer estimate of RSA, optimal
          when the signal to noise ratio is low, in ln(ms^2).

    Example
    ----------
    >>> import neurokit2 as nk
    >>>
    >>> # Download data
    >>> data = nk.data("bio_eventrelated_100hz")
    >>>
    >>> # Process the data
    >>> ecg_signals, info = nk.ecg_process(data["ECG"], sampling_rate=100)
    >>> rsp_signals, _ = nk.rsp_process(data["RSP"], sampling_rate=100)
    >>>
    >>> # Get RSA features
    >>> nk.hrv_rsa(ecg_signals, rsp_signals, info, sampling_rate=100, continuous=False) #doctest: +ELLIPSIS
    {'RSA_P2T_Mean': ...,
     'RSA_P2T_Mean_log': ...,
     'RSA_P2T_SD': ...,
     'RSA_P2T_NoRSA': ...,
     'RSA_PorgesBohrer': ...,
     'RSA_Gates_Mean': ...,
     'RSA_Gates_Mean_log': ...,
     'RSA_Gates_SD': ...}
    >>>
    >>> # Get RSA as a continuous signal
    >>> rsa = nk.hrv_rsa(ecg_signals, rsp_signals, info, sampling_rate=100, continuous=True)
    >>> rsa #doctest: +ELLIPSIS
            RSA_P2T  RSA_Gates
    0         ...         ...
    1         ...         ...
    2         ...         ...
    ...       ...         ...

    [15000 rows x 2 columns]
    >>> nk.signal_plot([ecg_signals["ECG_Rate"], rsp_signals["RSP_Rate"], rsa], standardize=True)

    References
    ------------
    - Servant, D., Logier, R., Mouster, Y., & Goudemand, M. (2009). La variabilité de la fréquence
      cardiaque. Intérêts en psychiatrie. L’Encéphale, 35(5), 423–428. doi:10.1016/j.encep.2008.06.016

    - Lewis, G. F., Furman, S. A., McCool, M. F., & Porges, S. W. (2012). Statistical strategies to
      quantify respiratory sinus arrhythmia: Are commonly used metrics equivalent?. Biological psychology,
      89(2), 349-364.

    - Zohar, A. H., Cloninger, C. R., & McCraty, R. (2013). Personality and heart rate variability:
      exploring pathways from personality to cardiac coherence and health. Open Journal of Social Sciences,
      1(06), 32.

    """
    signals, ecg_period, rpeaks, __ = _hrv_rsa_formatinput(ecg_signals, rsp_signals, rpeaks, sampling_rate)

    # Extract cycles
    rsp_cycles = _hrv_rsa_cycles(signals)
    rsp_onsets = rsp_cycles["RSP_Inspiration_Onsets"]
    rsp_peaks = np.argwhere(signals["RSP_Peaks"].values == 1)[:, 0]
    rsp_peaks = np.array(rsp_peaks)[rsp_peaks > rsp_onsets[0]]

    if len(rsp_peaks) - len(rsp_onsets) == 0:
        rsp_peaks = rsp_peaks[:-1]
    if len(rsp_peaks) - len(rsp_onsets) != -1:
        warn("Couldn't find rsp cycles onsets and centers. Check your RSP signal.", category=NeuroKitWarning)

    # Methods ------------------------

    # Peak-to-Trough
    rsa_p2t = _hrv_rsa_p2t(
        rsp_onsets, rpeaks, sampling_rate, continuous=continuous, ecg_period=ecg_period, rsp_peaks=rsp_peaks
    )
    # Porges-Bohrer
    rsa_pb = _hrv_rsa_pb(ecg_period, sampling_rate, continuous=continuous)

    # RSAsecondbysecond
    if window is None:
        window = 32  # 32 seconds
    input_duration = rpeaks[-1] / sampling_rate
    if input_duration >= window:
        rsa_gates = _hrv_rsa_gates(
            ecg_signals,
            rpeaks,
            sampling_rate=sampling_rate,
            window=window,
            window_number=window_number,
            continuous=continuous,
        )
    else:
        warn(
            "The duration of recording is shorter than the duration of the window (%s seconds)."
            " Returning RSA by Gates method as Nan."
            " Consider using a longer recording." % (window),
            category=NeuroKitWarning,
        )
        if continuous is False:
            rsa_gates = np.nan
        else:
            rsa_gates = np.full(len(rsa_p2t), np.nan)

    if continuous is False:
        rsa = {}  # Initialize empty dict
        rsa.update(rsa_p2t)
        rsa.update(rsa_pb)
        rsa.update(rsa_gates)
    else:
        rsa = pd.DataFrame({"RSA_P2T": rsa_p2t, "RSA_Gates": rsa_gates})

    return rsa


# =============================================================================
# Methods (Domains)
# =============================================================================
def _hrv_rsa_p2t(rsp_onsets, rpeaks, sampling_rate, continuous=False, ecg_period=None, rsp_peaks=None):
    """Peak-to-trough algorithm (P2T)"""

    # Find all RSP cycles and the Rpeaks within
    cycles_rri = []
    for idx in range(len(rsp_onsets) - 1):
        cycle_init = rsp_onsets[idx]
        cycle_end = rsp_onsets[idx + 1]
        cycles_rri.append(rpeaks[np.logical_and(rpeaks >= cycle_init, rpeaks < cycle_end)])

    # Iterate over all cycles
    rsa_values = np.full(len(cycles_rri), np.nan)
    for i, cycle in enumerate(cycles_rri):
        # Estimate of RSA during each breath
        RRis = np.diff(cycle) / sampling_rate
        if len(RRis) > 1:
            rsa_values[i] = np.max(RRis) - np.min(RRis)

    if continuous is False:
        rsa = {"RSA_P2T_Mean": np.nanmean(rsa_values)}
        rsa["RSA_P2T_Mean_log"] = np.log(rsa["RSA_P2T_Mean"])  # pylint: disable=E1111
        rsa["RSA_P2T_SD"] = np.nanstd(rsa_values, ddof=1)
        rsa["RSA_P2T_NoRSA"] = len(pd.Series(rsa_values).index[pd.Series(rsa_values).isnull()])
    else:
        rsa = signal_interpolate(
            x_values=rsp_peaks[~np.isnan(rsa_values)],
            y_values=rsa_values[~np.isnan(rsa_values)],
            x_new=np.arange(len(ecg_period)),
        )

    return rsa


def _hrv_rsa_pb(ecg_period, sampling_rate, continuous=False):
    """Porges-Bohrer method."""
    if continuous is True:
        return None

    # Re-sample at 2 Hz
    resampled = signal_resample(ecg_period, sampling_rate=sampling_rate, desired_sampling_rate=2)

    # Fit 21-point cubic polynomial filter (zero mean, 3rd order)
    # with a low-pass cutoff frequency of 0.095Hz
    trend = signal_filter(
        resampled, sampling_rate=2, lowcut=0.095, highcut=None, method="savgol", order=3, window_size=21
    )

    zero_mean = resampled - trend
    # Remove variance outside bandwidth of spontaneous respiration
    zero_mean_filtered = signal_filter(zero_mean, sampling_rate=2, lowcut=0.12, highcut=0.40)

    # Divide into 30-second epochs
    time = np.arange(0, len(zero_mean_filtered)) / 2
    time = pd.DataFrame({"Epoch Index": time // 30, "Signal": zero_mean_filtered})
    time = time.set_index("Epoch Index")

    epochs = [time.loc[i] for i in range(int(np.max(time.index.values)) + 1)]
    variance = []
    for epoch in epochs:
        variance.append(np.log(epoch.var(axis=0) / 1000))  # convert ms

    variance = [row for row in variance if not np.isnan(row).any()]

    return {"RSA_PorgesBohrer": pd.concat(variance).mean()}


# def _hrv_rsa_synchrony(ecg_period, rsp_signal, sampling_rate=1000, method="correlation", continuous=False):
#    """Experimental method
#    """
#    if rsp_signal is None:
#        return None
#
#    filtered_period = signal_filter(ecg_period, sampling_rate=sampling_rate,
#                                    lowcut=0.12, highcut=0.4, order=6)
#    coupling = signal_synchrony(filtered_period, rsp_signal, method=method, window_size=sampling_rate*3)
#    coupling = signal_filter(coupling, sampling_rate=sampling_rate, highcut=0.4, order=6)
#
#    if continuous is False:
#        rsa = {}
#        rsa["RSA_Synchrony_Mean"] = np.nanmean(coupling)
#        rsa["RSA_Synchrony_SD"] = np.nanstd(coupling, ddof=1)
#        return rsa
#    else:
#        return coupling


# def _hrv_rsa_servant(ecg_period, sampling_rate=1000, continuous=False):
#    """Servant, D., Logier, R., Mouster, Y., & Goudemand, M. (2009). La variabilité de la fréquence
# cardiaque. Intérêts en psychiatrie. L’Encéphale, 35(5), 423–428. doi:10.1016/j.encep.2008.06.016
#    """
#
#    rpeaks, _ = nk.ecg_peaks(nk.ecg_simulate(duration=90))
#    ecg_period = nk.ecg_rate(rpeaks) / 60 * 1000
#    sampling_rate=1000
#
#    if len(ecg_period) / sampling_rate <= 60:
#        return None
#
#
#    signal = nk.signal_filter(ecg_period, sampling_rate=sampling_rate,
#                           lowcut=0.1, highcut=1, order=6)
#    signal = nk.standardize(signal)
#
#    nk.signal_plot([ecg_period, signal], standardize=True)
#
#    troughs = nk.signal_findpeaks(-1 * signal)["Peaks"]
#    trough_signal = nk.signal_interpolate(x_values=troughs,
#                                          y_values=signal[troughs],
#                                          desired_length=len(signal))
#    first_trough = troughs[0]
#
#    # Initial parameters
#    n_windows = int(len(trough_signal[first_trough:]) / sampling_rate / 16)  # How many windows of 16 s
#    onsets = (np.arange(n_windows) * 16 * sampling_rate) + first_trough
#
#    areas_under_curve = np.zeros(len(onsets))
#    for i, onset in enumerate(onsets):
#        areas_under_curve[i] = sklearn.metrics.auc(np.linspace(0, 16, 16*sampling_rate),
#                                                   trough_signal[onset:onset+(16*sampling_rate)])
#    max_auc = np.max(areas_under_curve)
#
#    # Moving computation
#    onsets = np.arange(first_trough, len(signal)-16*sampling_rate, step=4*sampling_rate)
#    areas_under_curve = np.zeros(len(onsets))
#    for i, onset in enumerate(onsets):
#        areas_under_curve[i] = sklearn.metrics.auc(np.linspace(0, 16, 16*sampling_rate),
#                                                   trough_signal[onset:onset+(16*sampling_rate)])
#    rsa = (max_auc - areas_under_curve) / max_auc + 1
#
#    # Not sure what to do next, sent an email to Servant.
#    pass

# =============================================================================
# Second-by-second RSA
# =============================================================================


def _hrv_rsa_gates(ecg_signals, rpeaks, sampling_rate=1000, window=None, window_number=None, continuous=False):

    # Boundaries of rsa freq
    min_frequency = 0.12
    max_frequency = 0.40
    # Retrived IBI and interpolate it
    rri, sampling_rate = _hrv_get_rri(rpeaks, sampling_rate=sampling_rate, interpolate=True)

    # Re-sample at 4 Hz
    desired_sampling_rate = 4
    rri = signal_resample(rri, sampling_rate=sampling_rate, desired_sampling_rate=desired_sampling_rate)

    # Sanitize parameters
    overlap = int((window - 1) * desired_sampling_rate)
    nperseg = window * desired_sampling_rate
    if window_number is None:
        window_number = 8

    # Get multipeak window
    multipeak, weight = _get_multipeak_window(nperseg, window_number)

    for i in range(4):
        _, time, psd = signal_timefrequency(
            rri,
            sampling_rate=desired_sampling_rate,
            min_frequency=min_frequency,
            max_frequency=max_frequency,
            method="stft",
            window=window,
            window_type=multipeak[:, i],
            overlap=overlap,
            show=False,
        )
        if i == 0:
            rsa = np.zeros_like(psd)
        rsa = psd * weight[i] + rsa  # add weights
    meanRSA = np.log(2 * sum(rsa) / nperseg)

    # Sanitize output
    if continuous is False:
        rsa = {"RSA_Gates_Mean": np.nanmean(meanRSA)}
        rsa["RSA_Gates_Mean_log"] = np.log(rsa["RSA_Gates_Mean"])  # pylint: disable=E1111
        rsa["RSA_Gates_SD"] = np.nanstd(meanRSA, ddof=1)
    else:
        # For window=32, meanRSA is RSA from 16th second to xth second where x=recording
        # duration-16secs
        # Padding the missing first and list window/2 segments
        pad_length = window / 2
        time_start = np.arange(0, pad_length)
        time_end = np.arange(time[-1], time[-1] + pad_length)[1:]
        time = np.concatenate((time_start, time, time_end))

        rsa_start = np.full(len(time_start), meanRSA[0])
        rsa_end = np.full(len(time_end), meanRSA[-1])
        meanRSA = np.concatenate((rsa_start, meanRSA, rsa_end))

        # Convert to samples
        time = np.multiply(time, sampling_rate)

        rsa = signal_interpolate(time.astype(int), meanRSA, x_new=len(ecg_signals), method="monotone_cubic")
    return rsa


def _get_multipeak_window(nperseg, window_number=8):
    """Get Peak Matched Multiple Window
    References
    ----------
    Hansson, M., & Salomonsson, G. (1997). A multiple window method for estimation of peaked spectra.
    IEEE Transactions on Signal Processing, 45(3), 778-781.
    """
    K1 = 20  # Peak in dB
    K2 = 30  # Penalty value in dB

    B = (window_number + 2) / nperseg  # Resolution in spectrum

    loge = np.log10(np.exp(1))
    C = 2 * K1 / 10 / B / loge
    length = np.arange(1, nperseg).conj().transpose()
    r0 = 2 / C * (1 - np.exp(-C * B / 2))
    r_num = 2 * C - np.exp(-C * B / 2) * (
        2 * C * np.cos(np.pi * B * length) - 4 * np.pi * length * np.sin(np.pi * B * length)
    )

    r_den = C ** 2 + (2 * np.pi * length) ** 2
    r = np.divide(r_num, r_den)

    rpeak = np.append(r0, r)  # Covariance function peaked spectrum

    r = 2 * np.sin(np.pi * B * length) / (2 * np.pi * length)
    rbox = np.append(B, r)

    rpen = (
        10 ** (K2 / 10) * np.append(1, np.zeros((nperseg - 1, 1))) - (10 ** (K2 / 10) - 1) * rbox
    )  # Covariance function penalty function

    Ry = scipy.linalg.toeplitz(rpeak)
    Rx = scipy.linalg.toeplitz(rpen)
    RR = scipy.linalg.cholesky(Rx)
    C = scipy.linalg.inv(RR.conj().transpose()).dot(Ry).dot(scipy.linalg.inv(RR))
    _, Q = scipy.linalg.schur(C)
    F = scipy.linalg.inv(RR).dot(Q)
    RD = F.conj().transpose().dot(Ry).dot(F)
    RD = np.diag(RD)
    RDN = np.sort(RD)
    h = np.argsort(RD)

    FN = np.zeros((nperseg, nperseg))
    for i in range(len(RD)):
        FN[:, i] = F[:, h[i]] / np.sqrt(F[:, h[i]].conj().transpose().dot(F[:, h[i]]))

    RDN = RDN[len(RD) - 1 : 0 : -1]
    FN = FN[:, len(RD) - 1 : 0 : -1]

    weight = RDN[:window_number] / np.sum(RDN[:window_number])
    multipeak = FN[:, 0:window_number]

    return multipeak, weight


# =============================================================================
# Internals
# =============================================================================
def _hrv_rsa_cycles(signals):
    """Extract respiratory cycles."""
    inspiration_onsets = np.intersect1d(
        np.where(signals["RSP_Phase"] == 1)[0], np.where(signals["RSP_Phase_Completion"] == 0)[0], assume_unique=True
    )

    expiration_onsets = np.intersect1d(
        np.where(signals["RSP_Phase"] == 0)[0], np.where(signals["RSP_Phase_Completion"] == 0)[0], assume_unique=True
    )

    cycles_length = np.diff(inspiration_onsets)

    return {
        "RSP_Inspiration_Onsets": inspiration_onsets,
        "RSP_Expiration_Onsets": expiration_onsets,
        "RSP_Cycles_Length": cycles_length,
    }


def _hrv_rsa_formatinput(ecg_signals, rsp_signals, rpeaks=None, sampling_rate=1000):
    # Sanity Checks
    if isinstance(ecg_signals, tuple):
        ecg_signals = ecg_signals[0]
        rpeaks = None

    if isinstance(ecg_signals, pd.DataFrame):
        ecg_cols = [col for col in ecg_signals.columns if "ECG_Rate" in col]
        if ecg_cols:
            ecg_period = ecg_signals[ecg_cols[0]].values

        else:
            ecg_cols = [col for col in ecg_signals.columns if "ECG_R_Peaks" in col]
            if ecg_cols:
                ecg_period = signal_rate(rpeaks, sampling_rate=sampling_rate, desired_length=len(ecg_signals))
            else:
                raise ValueError(
                    "NeuroKit error: _hrv_rsa_formatinput():" "Wrong input, we couldn't extract" "heart rate signal."
                )
    if rsp_signals is None:
        rsp_cols = [col for col in ecg_signals.columns if "RSP_Phase" in col]
        if len(rsp_cols) != 2:
            edr = ecg_rsp(ecg_period, sampling_rate=sampling_rate)
            rsp_signals, _ = rsp_process(edr, sampling_rate)
            warn(
                "RSP signal not found. For this time, we will derive RSP"
                " signal from ECG using ecg_rsp(). But the results are"
                " definitely not reliable, so please provide a real RSP signal.",
                category=NeuroKitWarning,
            )
    elif isinstance(rsp_signals, tuple):
        rsp_signals = rsp_signals[0]

    if isinstance(rsp_signals, pd.DataFrame):
        rsp_cols = [col for col in rsp_signals.columns if "RSP_Phase" in col]
        if len(rsp_cols) != 2:
            edr = ecg_rsp(ecg_period, sampling_rate=sampling_rate)
            rsp_signals, _ = rsp_process(edr, sampling_rate)
            warn(
                "RSP signal not found. RSP signal is derived from ECG using ecg_rsp()." " Please provide RSP signal.",
                category=NeuroKitWarning,
            )

    if rpeaks is None:
        try:
            rpeaks = _signal_formatpeaks_sanitize(ecg_signals)
        except NameError:
            raise ValueError(
                "NeuroKit error: _hrv_rsa_formatinput(): " "Wrong input, we couldn't extract rpeaks indices."
            )
    else:
        rpeaks = _signal_formatpeaks_sanitize(rpeaks)

    signals = pd.concat([ecg_signals, rsp_signals], axis=1)

    # RSP signal
    if "RSP_Clean" in signals.columns:
        rsp_signal = signals["RSP_Clean"].values
    elif "RSP_Raw" in signals.columns:
        rsp_signal = signals["RSP_Raw"].values
    elif "RSP" in signals.columns:
        rsp_signal = signals["RSP"].values
    else:
        rsp_signal = None

    return signals, ecg_period, rpeaks, rsp_signal
