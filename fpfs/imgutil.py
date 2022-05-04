# FPFS shear estimator
# Copyright 20210905 Xiangchong Li.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the LSST License Statement and
# the GNU General Public License along with this program.  If not,
# see <http://www.lsstcorp.org/LegalNotices/>.
#
# python lib

import numpy as np

def try_numba_njit():
    try:
        import numba
        return numba.njit
    except ImportError:
        return lambda func: func

def _gauss_kernel(ny,nx,sigma,do_shift=False,return_grid=False):
    """
    Generate a Gaussian kernel on grids for np.fft.fft transform

    Parameters:
        ny (int):    		    grid size in y-direction
        nx (int):    		    grid size in x-direction
        sigma (float):		    scale of Gaussian in Fourier space
        do_shift (bool):        Whether do shift (True) or not (default: False)
        return_grid (bool):     return grids (True) or not (default: False)

    Returns:
        out (ndarray):          Gaussian on grids
        Y,X (typle):            grids for (y, x) axes (if return_grid)
    """
    out = np.empty((ny,nx))
    x   = np.fft.fftfreq(nx,1/np.pi/2.)
    y   = np.fft.fftfreq(ny,1/np.pi/2.)
    if do_shift:
        x=np.fft.fftshift(x)
        y=np.fft.fftshift(y)
    Y,X = np.meshgrid(y,x,indexing='ij')
    r2  = X**2.+Y**2.
    out = np.exp(-r2/2./sigma**2.)
    if not return_grid:
        return out
    else:
        return out,(Y,X)

def _gauss_kernel_rfft(ny,nx,sigma,return_grid=False):
    """
    Generate a Gaussian kernel on grids for np.fft.rfft transform

    Parameters:
        ny (int):    		    grid size in y-direction
        nx (int):    		    grid size in x-direction
        sigma (float):		    scale of Gaussian in Fourier space
        return_grid (bool):     return grids or not [default: False]

    Returns:
        out (ndarray):          Gaussian on grids
        Y,X (typle):            grids for (y, x) axes (if return_grid)
    """
    out = np.empty((ny,nx//2+1))
    x   = np.fft.rfftfreq(nx,1/np.pi/2.)
    y   = np.fft.fftfreq(ny,1/np.pi/2.)
    Y,X = np.meshgrid(y,x,indexing='ij')
    r2  = X**2.+Y**2.
    out = np.exp(-r2/2./sigma**2.)
    if not return_grid:
        return out
    else:
        return out,(Y,X)

def gauss_kernel(ny,nx,sigma,do_shift=False,return_grid=False,use_rfft=False):
    """
    Generate a Gaussian kernel in Fourier space on grids

    Parameters:
        ny (int):    		    grid size in y-direction
        nx (int):    		    grid size in x-direction
        sigma (float):		    scale of Gaussian in Fourier space
        do_shift (bool):	    center at (0,0) [True] or (ny/2,nx/2) [default: False]
        return_grid (bool):     return grids [True] or not [default: False]
        use_rfft (bool):        whether use rfft [True] or not [default: False]

    Returns:
        out (tuple):            Gaussian kernel and grids (if return_grid)
    """
    if not isinstance(ny,int):
        raise TypeError('ny should be int')
    if not isinstance(nx,int):
        raise TypeError('nx should be int')
    if not isinstance(sigma,(float,int)):
        raise TypeError('sigma should be float or int')
    if sigma<=0.:
        raise ValueError('sigma should be positive')

    if not use_rfft:
        return _gauss_kernel(ny,nx,sigma,do_shift,return_grid)
    else:
        if do_shift:
            raise ValueError('do not support shifting centroid if use_rfft=True')
        return _gauss_kernel_rfft(ny,nx,sigma,return_grid)

def getFouPow_rft(arrayIn: np.ndarray):
    """
    Get Fourier power function

    Parameters:
        arrayIn (ndarray):  image array (centroid does not matter)

    Returns:
        galpow (ndarray):   Fourier Power
    """

    ngrid   =   arrayIn.shape[0]
    tmp     =   np.abs(np.fft.rfft2(arrayIn))**2.
    tmp     =   np.fft.fftshift(tmp,axes=0)
    # Get power function and subtract noise power
    foupow  =   np.empty((ngrid,ngrid),dtype=np.float64)
    tmp2    =   np.roll(np.flip(tmp),axis=0,shift=1)
    foupow[:,:ngrid//2+1] =  tmp2
    foupow[:,ngrid//2:]   =  tmp[:,:-1]
    return foupow

def getFouPow(arrayIn: np.ndarray, noiPow=None):
    """
    Get Fourier power function

    Parameters:
        arrayIn (ndarray):  image array (centroid does not matter)

    Returns:
        out (ndarray):      Fourier Power (centered at (ngrid//2,ngrid//2))
    """
    out =   np.fft.fftshift(np.abs(np.fft.fft2(arrayIn))**2.).astype(np.float64)
    if isinstance(noiPow,float):
        out =   out-np.ones(arrayIn.shape)*noiPow*arrayIn.size
    elif isinstance(noiPow,np.ndarray):
        out =   out-noiPow
    return out

def getRnaive(arrayIn:np.ndarray):
    """
    A naive way to estimate Radius.
    Note, this naive estimation is heavily influenced by noise.

    Parameters:
        arrayIn (ndarray):  image array (centroid does not matter)

    Returns:
        sigma (ndarray):    effective radius
    """

    arrayIn2=   np.abs(arrayIn)
    # Get the half light radius of noiseless PSF
    thres   =   arrayIn2.max()*0.5
    sigma   =   np.sum(arrayIn2>thres)
    sigma   =   np.sqrt(sigma/np.pi)
    return sigma

def shapelets2D(ngrid,nord,sigma):
    """
    Generate shapelets function in Fourier space
    (only support square stamps: ny=nx=ngrid)

    Parameters:
        ngrid (int):    number of pixels in x and y direction
        nord (int):     radial order of the shaplets
        sigma (float):  scale of shapelets in Fourier space

    Returns:
        chi (ndarray):  2D shapelet basis in shape of [nord,nord,ngrid,ngrid]
    """

    mord    =   nord
    # Set up the r and theta function
    xy1d    =   np.fft.fftshift(np.fft.fftfreq(ngrid,d=sigma/2./np.pi))
    xfunc,yfunc=np.meshgrid(xy1d,xy1d)
    rfunc   =   np.sqrt(xfunc**2.+yfunc**2.)
    gaufunc =   np.exp(-rfunc*rfunc/2.)
    rmask   =   (rfunc!=0.)
    xtfunc  =   np.zeros((ngrid,ngrid),dtype=np.float64)
    ytfunc  =   np.zeros((ngrid,ngrid),dtype=np.float64)
    np.divide(xfunc,rfunc,where=rmask,out=xtfunc)
    np.divide(yfunc,rfunc,where=rmask,out=ytfunc)
    eulfunc = xtfunc+1j*ytfunc
    lfunc   =   np.zeros((nord+1,mord+1,ngrid,ngrid),dtype=np.float64)
    chi     =   np.zeros((nord+1,mord+1,ngrid,ngrid),dtype=np.complex64)
    # Set up l function
    lfunc[0,:,:,:]=1.
    lfunc[1,:,:,:]=1.-rfunc*rfunc+np.arange(mord+1)[None,:,None,None]
    #
    for n in range(2,nord+1):
        for m in range(mord+1):
            lfunc[n,m,:,:]=(2.+(m-1.-rfunc*rfunc)/n)*lfunc[n-1,m,:,:]-(1.+(m-1.)/n)*lfunc[n-2,m,:,:]
    for nn in range(nord+1):
        for mm in range(nn,-1,-2):
            c1=(nn-abs(mm))//2
            d1=(nn+abs(mm))//2
            cc=np.math.factorial(c1)+0.
            dd=np.math.factorial(d1)+0.
            cc=cc/dd/np.pi
            chi[nn,mm,:,:]=pow(-1.,d1)/sigma*pow(cc,0.5)*lfunc[c1,abs(mm),:,:]\
                    *pow(rfunc,abs(mm))*gaufunc*eulfunc**mm
    return chi

def fitNoiPow(ngrid,galPow,noiModel,rlim):
    """
    Fit the noise power from observed galaxy power

    Parameters:
        ngrid (int):      number of pixels in x and y direction
        galPow (ndarray): galaxy Fourier power function

    Returns:
        noiSub (ndarray): noise power to be subtracted
    """

    rlim2=  int(max(ngrid*0.4,rlim))
    indX=   np.arange(ngrid//2-rlim2,ngrid//2+rlim2+1)
    indY=   indX[:,None]
    mask=   np.ones((ngrid,ngrid),dtype=bool)
    mask[indY,indX]=False
    vl  =   galPow[mask]
    nl  =   noiModel[:,mask]
    par =   np.linalg.lstsq(nl.T,vl,rcond=None)[0]
    noiSub= np.sum(par[:,None,None]*noiModel,axis=0)
    return noiSub

def pcaimages(X,nmodes):
    """
    Estimate the principal components of array list X

    Parameters:
        X (ndarray):        input data array
        nmodes (int):       number of pcs to keep

    Returns:
        out (ndarray):      pc images,
        stds (ndarray):     stds on the axis
        eVout (ndarray):    eigen values
    """

    assert len(X.shape)==3
    # vectorize
    nobj,nn2,nn1=   X.shape
    dim         =   nn1*nn2
    # X is (x1,x2,x3..,xnobj).T [x_i is column vectors of data]
    X           =   X.reshape((nobj,dim))
    # Xave  = X.mean(axis=0)
    # X     = X-Xave
    # Xave  = Xave.reshape((1,nn2,nn1))
    # out =   np.vstack([Xave,V])

    # Get covariance matrix
    M   =   np.dot(X,X.T)/(nobj-1)
    # Solve the Eigen function of the covariance matrix
    # e is eigen value and eV is eigen vector
    # eV: (p1,p2,..,pnobj) [p_i is column vectors of parameters]
    e,eV=   np.linalg.eigh(M)
    # The Eigen vector tells the combination of ndata
    tmp =   np.dot(eV.T,X)
    # Rank from maximum eigen value to minimum
    # and only keep the first nmodes
    V   =   tmp[::-1][:nmodes]
    e   =   e[::-1][:nmodes+10]
    stds=   np.sqrt(e)
    out =   V.reshape((nmodes,nn2,nn1))
    eVout=  eV.T[:nmodes]
    return out,stds,eVout

def cut_img(img,rcut):
    """
    cutout img into postage stamp with width=2rcut

    Parameters:
        img (ndarray):  input image
        rcut (int):     cutout radius

    Returns:
        out (ndarray):  image in a stamp (cut-out)
    """
    ngrid   =   img.shape[0]
    beg     =   ngrid//2-rcut
    end     =   beg+2*rcut
    out     =   img[beg:end,beg:end]
    return out
