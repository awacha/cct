"""Functions for outlier detection"""

from typing import Tuple

import numpy as np
import scipy.stats.distributions


def outliers_zscore(data:np.ndarray, threshold:float=3) -> np.ndarray:
    """Find outliers based on the Z-score

    The Z-score is defined as:

    Z_i =(Y_i-mean(Y))/stddev(Y)

    :param data: the data set
    :type data: np.ndarray
    :param threshold: the threshold
    :type threshold: float
    :return: the indices of the outliers
    :rtype: np.ndarray (int64)
    """
    zscore = (data-np.nanmean(data))/np.nanstd(data, ddof=1)
    return np.arange(data.size)[np.abs(zscore)>threshold]

def outliers_zscore_mod(data:np.ndarray, threshold:float=3.5) -> np.ndarray:
    """Find outliers based on the modified Z-score proposed by Iglewicz and Hoaglin

    The modified Z-score is defined as:

    M_i = 0.6745*(Y_i-median(Y))/MAD

    and MAD is the median absolute deviation:

    MAD = median( | Y_i - median(Y) |)

    Boris Iglewicz and David Hoaglin (1993), The ASQC Basic References in Quality
    Control: Statistical Techniques. Ed. Edward F. Mykytka

    :param data: the data set
    :type data: np.ndarray
    :param threshold: the threshold (a value 3.5 is proposed by Iglewicz and Hoaglin)
    :type threshold: float
    :return: the indices of the outliers
    :rtype: np.ndarray (int64)
    """
    median_abs_dev = np.nanmedian(np.abs(data-np.nanmedian(data)))
    zscore_mod = 0.6745*(data-np.nanmedian(data))/median_abs_dev
    return np.arange(data.size)[np.abs(zscore_mod)>threshold]

def outliers_Tukey_iqr(data: np.array, threshold:float=1.5) -> np.ndarray:
    """Find outliers according to Tukey's interquartile range rule

    Those points are considered outliers which fall more than `threshold` times the
    interquartile range from the 1st or 3rd quartile.

    Tukey, John W (1977). Exploratory Data Analysis (ISBN 978-0-201-07616-5)

    :param data: the data set
    :type data: np.ndarray
    :param threshold: the threshold (defaults to 1.5, suggested by Tukey)
    :type threshold: float
    :return: the indices of the outliers
    :rtype: np.ndarray (int64)
    """
    q1, q3=np.percentile(data, [25, 75])
    iqr = q3-q1
    return np.arange(data.size)[np.logical_or(data<q1-(iqr*threshold), data>q3+(iqr*threshold))]

def outliers_Grubbs(data:np.ndarray, alpha:float, tail='both') -> Tuple[np.ndarray, float, float]:
    """Perform Grubbs' test for detecting a single outlier.

    H0: There is exactly one outlier in the data set
    Ha: There are no outliers in the data set

    Accept H0 if statistic > critical value

    Grubbs, Frank (February 1969), Technometrics, 11(1), pp. 1-21

    Stefansky, W. (1972), Technometrics, 14, pp. 469-479

    :param data: samples of a univariate normal distribution
    :type data: np.ndarray
    :param alpha: significance level
    :type alpha: float
    :param tail: which tail of the distribution should be checked
    :type tail: 'left', 'right' or 'both' (default)
    :return: the index of the invalid point in `data`, the test statistic and the critical value
    :rtype: np.ndarray(int64), float, float
    """
    N=data.size
    if tail=='right':
        G = (np.nanmax(data) - np.nanmean(data)) / np.nanstd(data, ddof=1)
        t = scipy.stats.distributions.t.ppf(1 - alpha / (N), N - 2)
        bad=np.array([np.nanargmax(data)], np.int64)
    elif tail == 'left':
        G = (np.nanmean(data) - np.nanmin(data)) / np.nanstd(data, ddof=1)
        t = scipy.stats.distributions.t.ppf(1 - alpha / (N), N - 2)
        bad = np.array([np.nanargmin(data)], np.int64)
    elif tail=='both':
        zscore=(data-np.nanmean(data))/np.nanstd(data, ddof=1)
        G=np.nanmax(np.abs(zscore))
        t=scipy.stats.distributions.t.ppf(1-alpha/(2*N),N-2)
        bad=np.arange(data.size)[np.abs(zscore)==G]
    else:
        raise ValueError(tail)
    critval=(N-1)/N**0.5*(t**2/(N-2+t**2))**0.5
    if G<critval:
        return np.zeros(0, np.int64), G, critval
    else:
        return bad, G, critval

def _tietjen_moore_critical_value(n:int, k:int, alpha:float, tail:str='both', Nsim:int=10000) -> float:
    """Calculate the critical values for the Tietjen-Moore outlier test

    :param n: the number of data points
    :type n: int
    :param k: the number of outliers
    :type k: int
    :param alpha: significance level
    :type alpha: float
    :param tail: which tail of the distribution should be checked
    :type tail: 'left', 'right' or 'both' (default)
    :param Nsim: number of simulations to get the critical value
    :type Nsim: int
    :returns: the critical value
    :rtype: float
    """
    def statistic(sorteddata, k):
        """Calculate the statistic when the last `k` data points are outliers"""
        notoutliers=sorteddata[:-k]
        notoutliersmean=np.nanmean(notoutliers)
        allmean=np.nanmean(sorteddata)
        return np.nansum((notoutliers-notoutliersmean)**2)/np.nansum((sorteddata-allmean)**2)
    # find critical region
    statref=np.empty(Nsim, np.double)
    for i in range(Nsim):
        simdata=np.random.randn(n)
        if tail=='right':
            simsorted=np.sort(simdata)
        elif tail=='left':
            simsorted=np.sort(simdata)[::-1]
        elif tail=='both':
            simsorted=simdata[np.lexsort((np.abs(simdata-np.nanmean(simdata)),))]
        else:
            raise ValueError(tail)
        statref[i]=statistic(simsorted, k)
    return np.quantile(statref, alpha)


def outliers_Tietjen_Moore(data:np.ndarray, k:int, alpha:float, tail='both', Nsim:int=10000) -> Tuple[np.ndarray, float, float]:
    """Perform a Tietjen-Moore test for outliers in a univariate data set.

    H0: there are exactly `k` outliers in the data set
    Ha: there are no outliers in the data set

    Accept H0 if test statistics < critical value

    Tietjen and Moore (August 1972), Technometrics, 14(3), pp. 583-597

    :param data: samples of a univariate normal distribution
    :type data: np.ndarray
    :param k: the number of outliers
    :type k: int
    :param alpha: significance level
    :type alpha: float
    :param tail: which tail of the distribution should be checked
    :type tail: 'left', 'right' or 'both' (default)
    :param Nsim: number of simulations to get the critical value
    :type Nsim: int
    :return: the indices of the invalid points in `data`, the test statistic and the critical value
    :rtype: np.ndarray, float, float
    """
    N=data.size
    if tail=='right':
        sortindex=np.lexsort((data,))
    elif tail=='left':
        sortindex=np.lexsort((data,))[::-1]
    elif tail=='both':
        sortindex=np.lexsort((np.abs(data-np.nanmean(data)),))
    else:
        raise ValueError(tail)
    # now `sortindex` is the index of the sort, i.e. data[sortindex] is sorted from lowest to largest. NaN will
    # be at the end!
    sorteddata=data[sortindex]
    def statistic(sorteddata, k):
        """Calculate the statistic when the last `k` data points are outliers"""
        notoutliers=sorteddata[:-k]
        notoutliersmean=np.nanmean(notoutliers)
        allmean=np.nanmean(sorteddata)
        return np.nansum((notoutliers-notoutliersmean)**2)/np.nansum((sorteddata-allmean)**2)
    q = _tietjen_moore_critical_value(N, k, alpha, tail, Nsim)
    stat=statistic(sorteddata, k)
    #print('Critical value:', q)
    #print('Statistic:', stat)
    if stat<q:
        return sortindex[-k:], stat, q
    else:
        return sortindex[:0], stat, q


def outliers_generalized_ESD(data:np.ndarray, max_number_of_outliers:int, alpha:float) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Perform the Generalized Extreme Studentized Deviate (ESD) test for finding outliers in a data set

    H0: There are up to `max_number_of_outliers` outliers in the data set
    Ha: there are no outliers in the data set

    Simulation studies by Rosner indicate that the critical value approximation
    is very accurate for n>=25 and reasonably accurate for n>=15.

    Rosner, Bernard (May 1983), Technometrics, 25(2), pp. 165-172.

    :param data: samples of a univariate normal distribution
    :type data: np.ndarray
    :param max_number_of_outliers: upper bound on the suspected number of outliers
    :type max_number_of_outliers: int
    :param alpha: significance level
    :type alpha: float
    :return: outlier indices, statistics (R_i), critical values (lambda_i)
    :rtype: np.ndarray (int64), np.ndarray (double), np.ndarray (double)
    """
    n=data.size
    R=np.empty(max_number_of_outliers, np.double)
    lambda_=np.empty(max_number_of_outliers, np.double)
    remaining=np.ones(data.shape, np.bool)
    rejected_indices=[]
    for i in range(max_number_of_outliers):
        # get the absolute deviation of the data, with respect to the mean of the remaining data points
        absdev=np.abs(data-np.mean(data[remaining]))
        # get the worst deviation (search only among the remaining data points)
        worst=np.max(absdev[remaining])
        # calculate the statistic
        R[i](worst/np.std(data[remaining], ddof=1))
        # remove the first data point which has the worst deviation
        index=np.argmin(np.abs(absdev-worst))
        rejected_indices.append(index)
        remaining[index]=0
        # calculate the critical value
        p=1-alpha/(2*(n-i))
        t=scipy.stats.distributions.t.ppf(p, n-i-2)
        lambda_[i]((n-i-1)*t/((n-i-2+t**2)*(n-i))**0.5)
        #print('{:>5d} {:10.5f} {:10.5f} {}'.format(i+1,R[i], lambda_[i], '*' if R[i]>lambda_[i] else ''))
    noutliers=max([i+1 for i in range(max_number_of_outliers) if R[i]>lambda_[i]])
    return np.array(rejected_indices[:noutliers], np.int64), R, lambda_

