"""Testing Module:
Cases to test:
    1) Basic run through with/without final cycle. Final cycle needs to be
       induced by final_tpost_write, final_cfl files, final inputs.in variables
    2) Restart in middle of combustion simulation
    3) Restart in middle of coolant simulation
    4) Restart in middle of final combustion cycle
    5) Restart during mapping/convergence checking/file saving in combustion/
       coolant step (need to implement tracking of parts to determine where
       to begin from) 
"""

from ruamel.yaml import YAML
import numpy as np
from .fileOps import getRecentFile
import os


nCombFailures = [0, 1, 3, 6, 0, 2, 3, 10, 0, 0, -1, 0]
nCoolFailures = [0, 1, 0, 2, 1, 6, 0, 1, 0, 0, 0, 1, -1, 0]






def makeCvgDone(fol):
    with open(fol+'/converge.done', 'w') as fid:
        fid.write('/n')

def makeRestartFile(fol, time, num=0):
    if num == 0:
        fname = fol + '/restart.rst'
    else:
        fname = '{0}/restart{1:04d}.rst'.format(fol,num)

    with open(fname,'w') as fid:
        fid.write('{0}\n'.format(time))


def getTimeFromRestartFileTest(resName):
    with open(resName, 'r') as fid:
        line = fid.readline()
        return float(line.strip())


def makeCoolantRestartFiles(fol, ShiftTime, ignoreRestart):
    resNum, resFile = getRecentFile('restart.rst', fol)

    if resNum == -2:
        resNum = 0
        lastResTime = 0
        makeRestartFile(fol, 'restart.rst', resNum)
    elif resNum == -1:
        if ignoreRestart:
            lastResTime = 0.0
        else:
            resFileFull = fol + '/' + resFile
            lastResTime = getTimeFromRestartFileTest(resFileFull)
    else:
        resFileFull = fol + '/' + resFile
        lastResTime = getTimeFromRestartFileTest(resFileFull)
    stopTime = lastResTime + ShiftTime

    resNum += 1
    lastResTime += 5.
    while lastResTime < stopTime-5:
        makeRestartFile(fol, lastResTime, resNum)
        remFile = fol + '/' + 'restart{0:04d}.rst'.format(resNum-3)
        if os.path.exists(remFile):
            os.system('rm {0}'.format(remFile))
        resNum += 1
        lastResTime += 5
    
    makeRestartFile(fol, stopTime, resNum)
    remFile = fol + '/' + 'restart{0:04d}.rst'.format(resNum-3)
    if os.path.exists(remFile):
        os.system('rm {0}'.format(remFile))


def makeRestartFiles(fol, ShiftTime, ignoreRestart, maxStopTime):
    resNum, resFile = getRecentFile('restart.rst', fol)
    
    if resNum == -2:
        resNum = 0
        lastResTime = 125.
        makeRestartFile(fol, 'restart.rst', resNum)
    elif resNum == -1:
        if ignoreRestart:
            lastResTime = 125.
        else:
            resFileFull = fol + '/' + resFile
            lastResTime = getTimeFromRestartFileTest(resFileFull)
    else:
        resFileFull = fol + '/' + resFile
        lastResTime = getTimeFromRestartFileTest(resFileFull)
    
    stopTime = min(lastResTime + ShiftTime,maxStopTime)
    resNum += 1
    lastResTime += 5.
    while lastResTime < stopTime-5:
        makeRestartFile(fol, lastResTime, resNum)
        remFile = fol + '/' + 'restart{0:04d}.rst'.format(resNum-3)
        if os.path.exists(remFile):
            os.system('rm {0}'.format(remFile))
        resNum += 1
        lastResTime += 5
    print('StopTime = ' + str(stopTime))
    makeRestartFile(fol, stopTime, resNum)
    remFile = fol + '/' + 'restart{0:04d}.rst'.format(resNum-3)
    if os.path.exists(remFile):
        os.system('rm {0}'.format(remFile))


def runTestSimulation(runFol, runInfo):
    iter = runInfo.iter()
    
    if runFol == runInfo.combustionFol():
        failName = 'curCombFailure'
        ignoreName = 'ignoreCombRestart'
        nFailures = nCombFailures[iter]
    else:
        failName = 'curCoolFailure'
        ignoreName = 'ignoreCoolRestart'
        nFailures = nCoolFailures[iter]
        
    if failName not in runInfo:
        runInfo[failName] = 0

    if runInfo[failName] < nFailures:
        print('Simulation a failure in {0} for iteration {1}'.format(
            runFol,runInfo[failName]))
        if runFol == runInfo.coolantFol():
            makeCoolantRestartFiles(runFol, 50., runInfo[ignoreName])
        else:
            makeRestartFiles(runFol, 50., runInfo[ignoreName],
                runInfo.combStopTime())
        runInfo[failName] += 1
    else:
        print('Simulation a successful completion in {0} for iteration \
{1}'.format(runFol,runInfo[failName]))
        if runFol == runInfo.coolantFol():
            makeCoolantRestartFiles(runFol, 50., runInfo[ignoreName])
        else:
            makeRestartFiles(runFol, 2000., runInfo[ignoreName],
                runInfo.combStopTime())
        runInfo[failName] = 0
        inFiles = os.listdir(runFol)
        for i in inFiles:
            if i[-3:] == '.in':
                with open(runFol + '/' + i.replace('.in','.out'),'w') as fid:
                    fid.write('\n')

        makeCvgDone(runFol)
    input("Press Enter to continue...")





