"""Functions for Mapping and Checking Convergence

Will copy transfer.out into run directory, use htc_map_64 to map
data to surface, format and move files generated by mapping into appropriate
simulation folder, check for convergence and save data in files for
comparison after next simulation

Variables
---------
HTCInputStr: String containing basic layout of htc_inputs.in to be used in
    generating htc_inputs.in files
headerCombustion: header for combustion boundary files
headerCoolant: header for coolant boundary files
coolantToCombustionColNames: column names for combustion boundary files
combustionToCoolantColNames: column names for coolant boundary files

Methods
-------
getCombustionTransferFile
getCoolantTransferFile:
combustionBCtoCoolantBC
coolantBCtoCombustionBC
getBoundaryData
getAverageDifference
getConvergenceString
checkRunConvergence
renameBoundaryFiles
genBCsFromMappedData
genHTCInputFiles
checkForMappingFiles
"""


import numpy as np
import os
from .fileOps import getNumberedFiles, callMoveFile, getBoundaryID
from .fileOps import createFolder
from . import IO# from .IO import IO.writeToStdErrFile, IO.writeToStdOutFile


##### Do Not Change (Used to generate boundary conditions files) ######
HTCInputStr = """
#----------------- Geometry Control -----------------#
2.000000e-03           tolerance
1.0                    grow_mult
1                      grow_interp_scheme
1.0                    scale_xyz
0.0                    rot_angle_x
0.0                    rot_angle_y
0.0                    rot_angle_z
0.0                    trans_x
0.0                    trans_y
0.0                    trans_z
sc-rx-ry-rz-tx-ty-tz   orderofoperations

#------------------ ABAQUS Control ------------------#
0                      read_abaqus

#------------------- HTC Control --------------------#
1e10                   max_htc
0                      use_bulk_fluid_temp

#------------------ Mapping Control -----------------#
0                      time_avg_option
1                      temp_map_option
1                      enforce_boundID_match
REPLACE_BOUNDARYID_MATCHING
0                      hit_location_output_files
0                      map_additional_variables
0                      use_convective_ht


#----------------- Output Control -------------------#
0                      ensight_outputfiles
0                      gmv_outputfiles
0                      fieldview_outputfiles
0                      tecplot_outputfiles
REPLACE_DEDICATED_BOUNDARY_OUTPUT


#------------------- Time Control -------------------#
0                      start_time
REPLACE_END_TIME       end_time
1                      startoption


#----------------- Moving Boundaries ----------------#
0                      num_valve_entries
"""


# Top of boundary input file for combustion (time in crank angle 
# degrees) and coolant (time in seconds) simulations
headerCombustion = 'SPATIAL\n1.0\tscale_xyz\n0.0\ttrans_x\n0.0\ttrans_y\
\n0.0\ttrans_z\nx\trot_axis\n0.0\trot_angle\n\n0.0 crank\n'
headerCoolant = 'SPATIAL\n1.0\tscale_xyz\n0.0\ttrans_x\n0.0\ttrans_y\n0.0\
\ttrans_z\nx\trot_axis\n0.0\trot_angle\n\n0.0 second\n'


# column names for boundary input files for combustion (uses convection)
# and coolant (uses temperature) simulations
coolantToCombustionColNames = 'x\ty\tz\tRef_Temp\tConv_HTC'
combustionToCoolantColNames = 'x\ty\tz\ttemperature'


def getCombustionTransferFile(runInfo):
    """This function will concatenate transfer.out files in the event that a
    combustion simulation is restarted. When restarting, the script will write
    previous transfer#.out to transfer.out, so at most will only need to
    concatenate 2 files
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing state of job.

    Returns
    -------
    bool:
        Bool indicating that combustion transfer file was successfully
        obtained and copied into main run directory
    """

    combustionFolder = runInfo.combustionFol()

    transferFiles = getNumberedFiles('transfer.out', combustionFolder)

    if len(transferFiles) == 0:
        runInfo.setSimError()
        IO.writeToStdErrFile('No transfer.out files found in combustion \
simulation folder')
        return False

    elif len(transferFiles) == 1:
        transFile = combustionFolder + '/' + transferFiles[0]
        if checkDataInTransferFile(transFile) == False:
            runInfo.setSimError()
            IO.writeToStdErrFile('only transfer#.out file has no data. \
Cancelling job')
            return False

        copyStr = 'cp {0} transferTmp.out'.format(transFile)
        os.system(copyStr)
        return True

    elif len(transferFiles) == 2:
        if 'transfer.out' not in transferFiles:
            runInfo.setSimError()
            IO.writeToStdErrFile('Two transfer#.out files found in folder, \
but no transfer.out file found. Cancelling job')
            return False

        transFile1 = combustionFolder + '/transfer.out'
        
        del transferFiles[transferFiles.index('transfer.out')]

        transFile2 = combustionFolder + '/' + transferFiles[0]
        file1HasData = checkDataInTransferFile(transFile1)
        file2HasData = checkDataInTransferFile(transFile2)
                
        if file1HasData == False:
            if file2HasData == True:
            # no data in transfer.out, just using transFile2
                copyStr = 'cp {0} transferTmp.out'.format(transFile2)
                os.system(copyStr)
                return True
            else:
                runInfo.setSimError()
                IO.writeToStdErrFile('Neither transfer.out files in combustion \
folder contain data')
                return False

        elif file2HasData == False:
            copyStr = 'cp {0} transferTmp.out'.format(transFile1)
            os.system(copyStr)
            return True
        else:
            copyStr1 = 'cp {0} transferTmp.out'.format(transFile1)
            os.system(copyStr1)
            catStr = 'tail -n +2 {0} >> transferTmp.out'.format(transFile2)
            os.system(catStr)
            return True

    else:
        runInfo.setSimError()
        IO.writeToStdErrFile('Combustion folder contains more than 2 \
transfer.out files, which should not occur')
        return False


def checkDataInTransferFile(fname):
    """Checks to ensure that transfer.out file has data in it.
    
    Parameters
    ----------
    fname: str
        Name of transfer.out file.

    Returns
    -------
    bool:
        Bool indicating transfer.out file does have data
    """

    count = 0
    with open(fname,'r') as fid:
        for i in fid:
            count += 1
            if count > 20:
                return True
    return False


def getCoolantTransferFile(runInfo):
    """in the event that a coolant simulation is restarted, the most recent
    transfer.out file may not contain any data. Therefore, this function will
    check each transfer.out file starting with the most recent until it finds
    the last boundary data output. It will copy this data into transferTmp.out
    for use in mapping.

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing state of job.

    Returns
    -------
    bool:
        Bool indicating that coolant transfer file was successfully
        obtained and copied into main run directory
    """
    
    coolantFolder = runInfo.coolantFol()
    transferFiles = getNumberedFiles('transfer.out', coolantFolder)

    if len(transferFiles) == 0:
        runInfo.setSimError()
        IO.writeToStdErrFile('No transfer.out files found in coolant \
simulation folder')
        return False

    
    # check transfer#.out files starting with highest restart number to
    # find first file containing data
    ind = len(transferFiles) - 1
    while True:
        if ind == -1:
            runInfo.setSimError()
            IO.writeToStdErrFile('No transfer.out files in coolant folder \
contained data. Cancelling job')
            return False
    
        fullName = coolantFolder + '/' + transferFiles[ind]
        if checkDataInTransferFile(fullName):
            fileWithData = fullName
            break
        ind -= 1
    
    # create transferTmp.out with correct heading (function will append
    # last saved data starting with the line after the time to bottom of
    # this file)
    with open('transferTmp.out','w') as fid:
        fid.write(" # CONVERGE Release Build 2.4.33/  Nov 13, 2020       \
Run Date:Fri Dec 11 13:41:27 2020\n\n")
        fid.write(" Crank                  =  1.0000000000000        (DEG)\n")
    
    os.system('grep -n ' + fileWithData + ' -e "Ave Gas Temperature" > \
transData.tmp')
    with open('transData.tmp','r') as fid:
        lines = fid.readlines()
        lastTimeLine = int(lines[-1].split(':')[0])
    os.system('rm transData.tmp')

    lastTStepStr = 'tail -n +' + lastTimeLine + fileWithData + ' >> \
transferTmp.out'

    os.system(lastTStepStr)
    return True


def combustionBCtoCoolantBC(runInfo):
    """Maps transfer.out data from combustion simulation to boundary condition
    files in coolant simulation.
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing state of job.
    """

    gotFile = getCombustionTransferFile(runInfo)
    if gotFile == False:
        IO.writeToStdErrFile('Error, unable to get combustion transfer file. \
Stopping simulation')
        return

    copyStr2 = 'cp ./htc_inputs_combustion.in ./htc_inputs.in'
    os.system(copyStr2)

    os.system('./htc_map_64 engineToCoolantInterface.dat transferTmp.out \
>> log.htcMapCombustion')

    for i in runInfo['boundaries']:
        genBCsFromMappedData('coolant', i, runInfo.coolantFol())


def coolantBCtoCombustionBC(runInfo):
    """Maps transfer.out data from coolant simulation to boundary condition
    files in combustion simulation.
    
    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing state of job.
    """
    
    gotFile = getCoolantTransferFile()
    if gotFile == False:
        IO.writeToStdErrFile('Failure obtaining data from coolant transfer.out \
file. Stopping simulation')
        return

    copyStr2 = 'cp ./htc_inputs_coolant.in ./htc_inputs.in'
    os.system(copyStr2)

    os.system('./htc_map_64 engineToCoolantInterface.dat transferTmp.out \
>> log.htcMapCoolant')
    
    for i in runInfo['boundaries']:
        genBCsFromMappedData('combustion', i, runInfo.combustionFol())


def getBoundaryData(boundName, runType):
    """Collects mapped data from previous iteration, and current iteration
    and return average, min and max difference between two. Used to check
    covergence. Return Nones if the previous iterations data doesnt exist.
    
    Parameters
    ----------
    boundName: str
        Name of boundary to get data for
    runType: str
        Simulation type comparing data from. Either combustion or coolant

    Returns
    -------
    np.array:
        minimum difference in temporal boundary values
    np.array:
        maximum difference in temporal boundary values
    np.array:
        average difference in temporal boundary values        
    """

    if runType.lower() == 'combustion':
        folName = 'prevCombustionData'
    else:
        folName = 'prevCoolantData'

    newBnd = 'htc_triangles_' + boundName + '.map'
    oldBnd = folName + '/' + newBnd
    if not(os.path.exists(oldBnd)):
        return None, None, None
    return getAverageDifference(oldBnd, newBnd)


def getAverageDifference(oldBnd, newBnd):
    """Calculates avg, min and max difference in each boundary value for
    two different files (represening current and previous iteration values).
    Boundary values include the surface temperature, heat flux, htc, and 
    fluid temperature. Used when checking convergence. Note: returns absolute
    difference in values and not percent difference.

    Parameters
    ----------
    oldBnd: str
        Name of file containing data from previous iteration.
    runType: str
        Name of file containing data from current iteration.

    Returns
    -------
    np.array:
        minimum temporal difference in boundary values
    np.array:
        maximum temporal difference in boundary values
    np.array:
        average temporal difference in boundary values
    """

    # Load data
    oldData = np.loadtxt(oldBnd,comments='#')
    newData = np.loadtxt(newBnd,comments='#')

    # Check that data locations are same in both files (ind 1 = xloc, ind 2 = 
    # yloc and ind 3 = zloc). If differences in location, ignore data points
    # and print warning. Note: This should not occur and likely indicates
    # an error, so it should be investigated if this occurs.
    cmpLocs = np.bitwise_and(oldData[:,1] == newData[:,1], 
        np.bitwise_and(oldData[:,2] == newData[:,2],
        oldData[:,3] == newData[:,3]))
    if(cmpLocs.sum() < oldData.shape[0]):
        IO.writeToStdErrFile('Warning: Not Comparing all data along {0} due to \
differences in data sets'.format(newBnd))

    # Calculate differences between 4 variables and return min, max and avg
    # difference
    oldData = oldData[cmpLocs,5:9]
    newData = newData[cmpLocs,5:9]
    dataDiff = np.abs(oldData-newData)
    maxDiff = dataDiff.max(axis=0)
    minDiff = dataDiff.min(axis=0)
    avgDiff = dataDiff.mean(axis=0)
    return minDiff, maxDiff, avgDiff


def getConvergenceString(runInfo, minval,maxval,avgval,name):
    """Generates a string to print indicating the min, max and avg difference
    in values between iterations for a given variable name. Implemented to
    simplify checkRunConvergence function below. 

    Parameters
    ----------
    runInfo: RunInfoClass
        Contains job state and convergence criteria
    minval: np.array
        min difference in boundary values for each variable
    maxval: np.array
        max difference in boundary values for each variable
    avgval: np.array
        average difference in boundary values for each variable
    name: str
        Name of variable to be printed. (Either flux, boundarytemp, htc
        or fluidtemp)

    Returns
    -------
    str:
        String with convergence data for the given variable
    """

    if name.lower() == 'flux':
        index = 1
        cvgVal = maxval[1] <= runInfo['fluxTol']
    elif name.lower() == 'boundarytemp':
        index = 0
        cvgVal = maxval[0] <= runInfo['boundaryTempTol']
    elif name.lower() == 'htc':
        index = 2
        cvgVal = maxval[2] <= runInfo['htcTol']
    elif name.lower() == 'fluidtemp':
        index = 3
        cvgVal = maxval[3] <= runInfo['fluidTempTol']
    if cvgVal:
        cvgValStr = 'Converged'
    else:
        cvgValStr = 'Not Converged'

    return ('\t\t{0} ({1}): min = {2}, max = {3}, avg = {4}\n'.format(name,
            cvgValStr, minval[index],maxval[index],avgval[index]))


def checkRunConvergence(runInfo, runType):
    """Checks simulation for convergence, prints convergence data to stdout
    and separate convergence file and returns convergence information. Prints
    data for all mapped boundaries together and individually.

    Parameters
    ----------
    runInfo: RunInfoClass
        Object containing state of job.
    runType: str
        Simulation being checked for convergence. Either 'coolant' or
        'combustion'.
    
    Returns
    -------
    bool:
        Boolean indicating if simulation has converged
    """

    iterNumber = runInfo.iter()

    # Name of file to write convergence information to
    if runType.lower() == 'combustion':
        outFile = 'combustionConvergence.txt'
    else:
        outFile = 'coolantConvergence.txt'

    # If first iteration, no data to compare with, so return. If simulation
    # if restarted without convergence output file, assumes that previous
    # iterations data also doesnt exist and returns. Iteration number is
    # checked also to ensure that function doesnt check data accidently
    # left in run folder from previous job
    if not os.path.exists(outFile) or iterNumber == 0:
        with open(outFile,'w') as fid:
            # If file doesnt exist, create it and add header
            fid.write('Convergence Data for ' + runType + ' Simulations\n')
            return False


    with open(outFile,'a') as fid:
        fid.write('\nIteration Number ' + str(iterNumber) + ':\n')
        fullCvg = True

        # Iterate through boundaries, and print convergence results while
        # tracking total convergence with fullCvg bool
        for i in runInfo['boundaries']:

            minDiff, maxDiff, avgDiff = getBoundaryData(i, runType)
            if minDiff is None:
                fullCvg = False
                continue
            # columns are (0) boundary Temp, (1) Flux, (2) HTC, (3) Fluid Temp

            # if mapping from combustion, compare flux and boundary temps
            if runType.lower() == 'combustion':
                if (maxDiff[1] <= runInfo['fluxTol'] and
                    maxDiff[0] <= runInfo['boundarytempTol']):
                    fid.write('\t' + i + ' Converged:')
                else:
                    fullCvg = False
                    fid.write('\t' + i + ' Not Converged:')

                fid.write(getConvergenceString(runInfo, minDiff, maxDiff,
                                               avgDiff, 'Flux'))
                fid.write(getConvergenceString(runInfo, minDiff, maxDiff,
                                               avgDiff, 'boundarytemp'))
            # if mapping from coolant, compare flux, htc and fluid temps
            else:
                if (maxDiff[1] <= runInfo['fluxTol'] and
                    maxDiff[2] <= runInfo['htcTol'] and
                    maxDiff[3] <= runInfo['fluidTempTol']):
                    fid.write('\t' + i + ' Converged:')
                else:
                    fullCvg = False
                    fid.write('\t' + i + ' Not Converged:')

                fid.write(getConvergenceString(runInfo, minDiff, maxDiff,
                                               avgDiff, 'Flux'))
                fid.write(getConvergenceString(runInfo, minDiff, maxDiff,
                                               avgDiff, 'fluidTemp'))
                fid.write(getConvergenceString(runInfo, minDiff, maxDiff,
                                               avgDiff, 'HTC'))
                
    return fullCvg


# renames output from htc_map_64 to new names to store
# for checking convergence during next iteration
def renameBoundaryFiles(runInfo, simType):
    """Renames files generated by htc_map_64 to keep for checking for
    convergence on next iteration.

    Parameters
    ----------
    runInfo: RunInfoClass
        Object containing state of simulation
    simType: str
        Simulation type that data was generated from.
    """

    if simType.lower() == 'combustion':
        folName = 'prevCombustionData'
    else:
        folName = 'prevCoolantData'
    
    # Create folder just in case it doesnt already exist
    createFolder(folName)
    
    for i in runInfo['boundaries']:
        oldBnd = 'htc_triangles_' + i + '.map'
        newBnd = folName + '/' + oldBnd
        
        callMoveFile(oldBnd, newBnd)

# Mapping Combustion Data to Coolant BCs
def genBCsFromMappedData(rType, bndName, folOut='.'):
    """Converts data generated by htc_map_64 to form needed by CVG for
    boundary data files. 

    Parameters
    ----------
    rType: str
        Simulation type that data was generated from.
    bndName: str
        Name of boundary
    folOut: str
        Directory to add newly generated boundary file to
    """

    fileIn = 'htc_triangles_' + bndName + '.map'
    fileOut = folOut + '/' + bndName + '_spatialTemp.in'
    
    bndData = np.loadtxt(fileIn,comments='#')
    if 'cool' in rType.lower():
        fileHeader = headerCoolant + combustionToCoolantColNames
        outData = bndData[:,[1,2,3,5]]
    else:
        fileHeader = headerCombustion + coolantToCombustionColNames
        outData = bndData[:,[1,2,3,8,7]]

    np.savetxt(fileOut, outData, delimiter='\t', comments='',
               header=fileHeader)


def genHTCInputFiles(runInfo):
    """Generates htc_inputs.in file for use by htc_map_64. Slightly different
    files for coolant and combustion, so one will be generated for each
    simulation with corresponding simulation type appended to file name. When
    mapping data, the appropriate file will be renamed to htc_inputs.in before
    calling htc_map_64.

    Parameters
    ----------
    runInfo: RunInfoClass
        Object containing state of simulation
    """

    nBounds = runInfo.nBoundaries()
    BIDMatching = str(nBounds) + 15*' ' + 'num_boundaries\n'
    OutputFiles = str(nBounds) + 15*' ' + 'dedicatedboundaryoutputfiles\n'
    for bName in runInfo['boundaries']:
        coolID = getBoundaryID(bName, runInfo.coolantFol())
        combID = getBoundaryID(bName, runInfo.combustionFol())
        if coolID != combID:
            IO.writeToStdErrFile('Error: Boundaries being mapped must use same \
boundary IDs in coolant and combustion simulations.\n')
            IO.writeToStdErrFile('\t{0} has ID = {1} in coolant simulation and \
in combustion simulation'.format(coolID, combID))
            return False
        elif combID is None:
            IO.writeToStdErrFile('Error: Boundary named {0} cannot be found in \
combustion simulation boundary.in file.'.format(combID))
            return False
        elif coolID is None:
            IO.writeToStdErrFile('Error: Boundary named {0} cannot be found in \
coolant simulation boundary.in file.'.format(coolID))
            return False
        OutputFiles += bName + 15*' ' + 'name\n1' + 15*' ' + 'numboundaries\n'
        OutputFiles += str(coolID) + 15*' ' + 'boundary\n'
        BIDMatching += str(coolID) + 15*' ' + 'boundID\n'

    baseString = HTCInputStr.replace('REPLACE_BOUNDARYID_MATCHING',
        BIDMatching)
    baseString = baseString.replace('REPLACE_DEDICATED_BOUNDARY_OUTPUT',
        OutputFiles)

    with open('htc_inputs_coolant.in','w') as fid:
        fid.write(baseString.replace('REPLACE_END_TIME','2'))
    with open('htc_inputs_combustion.in','w') as fid:
        fid.write(baseString.replace('REPLACE_END_TIME','100000000'))



def checkForMappingFiles(runInfo):
    """Checks that htc_inputs_coolant.in, htc_inputs_combustion.in, 
    htc_map_64 and surface for mapping files are located in run directory.

    Parameters
    ----------
    runInfo: RunInfoClass
        Run information containing name of combustion folder.

    Returns
    -------
    bool:
        Bool indicating that all files are found in directory
    """

    IO.writeToStdOutFile('Checking all needed mapping files exist')
    if not(os.path.exists('htc_map_64')):
        IO.writeToStdErrFile('Error: Run directory does not contain htc_map_64 \
executable.')
        return False
    elif not(os.path.exists('htc_inputs_combustion.in')):
        IO.writeToStdErrFile('Error: Run directory does not contain \
htc_inputs_combustion.in for mapping from combustion simulation.\nThis should \
have been created during initialization.')
        return False
    elif not(os.path.exists('htc_inputs_coolant.in')):
        IO.writeToStdErrFile('Error: Run directory does not contain \
htc_inputs_coolant.in for mapping from coolant simulation.\nThis should \
have been created during initialization.')
        return False
    elif not(os.path.exists(runInfo['mapSurfaceFile'])):
        IO.writeToStdErrFile('Error: Run directory does not contain \
surface for mapping boundary data. This was checked during initialization, \
so it must have been deleted')
        return False

    return True
