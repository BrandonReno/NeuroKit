# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd


def eda_intervalrelated(data):
    """Performs EDA analysis on longer periods of data (typically > 10 seconds), such as resting-state data.

    Parameters
    ----------
    data : Union[dict, pd.DataFrame]
        A DataFrame containing the different processed signal(s) as
        different columns, typically generated by `eda_process()` or
        `bio_process()`. Can also take a dict containing sets of
        separately processed DataFrames.

    Returns
    -------
    DataFrame
        A dataframe containing the analyzed EDA features. The analyzed
        features consist of the following:
        - *"SCR_Peaks_N"*: the number of occurrences
        of Skin Conductance Response (SCR).
        - *"SCR_Peaks_Amplitude_Mean"*: the mean amplitude of the SCR peak
        occurrences.

    See Also
    --------
    bio_process, eda_eventrelated

    Examples
    ----------
    >>> import neurokit2 as nk
    >>>
    >>> # Download data
    >>> data = nk.data("bio_resting_8min_100hz")
    >>>
    >>> # Process the data
    >>> df, info = nk.eda_process(data["EDA"], sampling_rate=100)
    >>>
    >>> # Single dataframe is passed
    >>> nk.eda_intervalrelated(df) #doctest: +SKIP
    >>>
    >>> epochs = nk.epochs_create(df, events=[0, 25300], sampling_rate=100, epochs_end=20)
    >>> nk.eda_intervalrelated(epochs) #doctest: +SKIP

    """

    intervals = {}

    # Format input
    if isinstance(data, pd.DataFrame):
        peaks_cols = [col for col in data.columns if "SCR_Peaks" in col]
        if len(peaks_cols) == 1:
            intervals["Peaks_N"] = data[peaks_cols[0]].values.sum()
        else:
            raise ValueError(
                "NeuroKit error: eda_intervalrelated(): Wrong"
                "input, we couldn't extract SCR peaks."
                "Please make sure your DataFrame"
                "contains an `SCR_Peaks` column."
            )
        amp_cols = [col for col in data.columns if "SCR_Amplitude" in col]
        if len(amp_cols) == 1:
            intervals["Peaks_Amplitude_Mean"] = np.nansum(data[amp_cols[0]].values) / data[peaks_cols[0]].values.sum()
        else:
            raise ValueError(
                "NeuroKit error: eda_intervalrelated(): Wrong"
                "input, we couldn't extract SCR peak amplitudes."
                "Please make sure your DataFrame"
                "contains an `SCR_Amplitude` column."
            )

        eda_intervals = pd.DataFrame.from_dict(intervals, orient="index").T.add_prefix("SCR_")

    elif isinstance(data, dict):
        for index in data:
            intervals[index] = {}  # Initialize empty container

            intervals[index] = _eda_intervalrelated_formatinput(data[index], intervals[index])
        eda_intervals = pd.DataFrame.from_dict(intervals, orient="index")

    return eda_intervals


# =============================================================================
# Internals
# =============================================================================


def _eda_intervalrelated_formatinput(interval, output={}):
    """Format input for dictionary."""
    # Sanitize input
    colnames = interval.columns.values
    if len([i for i in colnames if "SCR_Peaks" in i]) == 0:
        raise ValueError(
            "NeuroKit error: eda_intervalrelated(): Wrong"
            "input, we couldn't extract SCR peaks."
            "Please make sure your DataFrame"
            "contains an `SCR_Peaks` column."
        )
        return output  # pylint: disable=W0101
    if len([i for i in colnames if "SCR_Amplitude" in i]) == 0:
        raise ValueError(
            "NeuroKit error: eda_intervalrelated(): Wrong"
            "input we couldn't extract SCR peak amplitudes."
            "Please make sure your DataFrame"
            "contains an `SCR_Amplitude` column."
        )
        return output  # pylint: disable=W0101

    peaks = interval["SCR_Peaks"].values
    amplitude = interval["SCR_Amplitude"].values

    output["SCR_Peaks_N"] = np.sum(peaks)
    if np.sum(peaks) == 0:
        output["SCR_Peaks_Amplitude_Mean"] = np.nan
    else:
        output["SCR_Peaks_Amplitude_Mean"] = np.sum(amplitude) / np.sum(peaks)

    return output
