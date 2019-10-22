'''
Functions and classes for working with the freefield dome and arc.
'''
# TODO: speaker numbers and RX8 indices should be zero-based for consistency!

import time
from pathlib import Path
import collections
import numpy
import slab
import win32com.client
from freefield import camera

# internal variables here:
_verbose = False
_speaker_config = None
_calibration_file = None
_calibration_filter = None
_speaker_table = None
_procs=None
_location = Path(__file__).resolve().parents[0]

def initialize_devices(ZBus=True, RX81_file=None, RX82_file=None, RP2_file=None, RX8_file=None, cam=False, connection='GB'):
	'Initialize the ZBus, RX8s, and RP2 with the respective rcx files.'
	global _procs
	if not _speaker_config:
		raise ValueError("Please set device to 'arc' or 'dome' before initialization!")
	printv('Initializing TDT rack.')
	RX81, RX82, RP2, ZB = None, None, None, None
	if RX8_file: RX81_file, RX82_file = RX8_file, RX8_file  # use this file for both processors
	if RX81_file: RX81 = _initialize_processor(device_type='RX8', rcx_file=str(RX81_file), index=1, connection=connection)
	if RX82_file: RX82 = _initialize_processor(device_type='RX8', rcx_file=str(RX82_file), index=2, connection=connection)
	if RP2_file: RP2 = _initialize_processor(device_type='RP2', rcx_file=str(RP2_file), index=1, connection=connection)
	if ZBus: ZB = _initialize_processor(device_type='ZBus')
	if cam:
		camera.init()
	proc_tuple = collections.namedtuple('TDTrack', 'ZBus RX81 RX82 RP2')
	_procs = proc_tuple(ZBus=ZB, RX81=RX81, RX82=RX82, RP2=RP2)


def _initialize_processor(device_type=None, rcx_file=None, index=1, connection='GB'):
	if device_type.lower() == 'zbus':
		try:
			ZB = win32com.client.Dispatch('ZBUS.x')
		except win32com.client.pythoncom.com_error as err:
			raise ValueError(err)
		if ZB.ConnectZBUS(connection):
			printv('Connected to ZBUS.')
		else: raise ConnectionError('Failed to connect to ZBUS.')
		return ZB
	else: # it's an RP2 or RX8
		try: # load RPco.x
			RP = win32com.client.Dispatch('RPco.X')
		except win32com.client.pythoncom.com_error as err:
			raise ValueError(err)
		if device_type == "RP2":
			if RP.ConnectRP2(connection, index): # connect to device
				printv("Connected to RP2")
			else: raise ConnectionError('Failed to connect to RP2.')
		elif device_type == "RX8":
			if RP.ConnectRX8(connection, index):  # connect to device
				printv("Connected to RX8")
			else: raise ConnectionError('Failed to connect to RX8.')
		else: raise ValueError('Unknown device type!')
		if not RP.ClearCOF(): raise ValueError('ClearCOF failed')
		if not rcx_file[-4:] == '.rcx':
			rcx_file += '.rcx'
		if RP.LoadCOF(rcx_file):
			printv(f'Circuit {rcx_file} loaded.')
		else: raise ValueError(f'Failed to load {rcx_file}.')
		if RP.Run():
			printv('Circuit running')
		else: raise ValueError(f'Failed to run {rcx_file}.')
		return RP

def halt():
	'Halt all processors in the rack (all elements that have a Halt method).'
	for proc_name in _procs._fields:
		proc = getattr(_procs, proc_name)
		if hasattr(proc, 'Halt'):
			printv(f'Halting {proc_name}.')
			proc.Halt()

def set_speaker_config(setup='arc'):
	'Set the freefield setup to use (arc or dome).'
	global _speaker_config, _calibration_filter, _speaker_table
	if setup == 'arc':
		_speaker_config = 'arc'
		_calibration_file = _location / Path('calibration_filter_arc.npy')
		table_file = _location / Path('speakertable_arc.txt')
	elif setup == 'dome':
		_speaker_config = 'dome'
		_calibration_file = _location / Path('calibration_filter_dome.npy')
		table_file = _location / Path('speakertable_dome.txt')
	else: raise ValueError("Unknown device! Use 'arc' or 'dome'.")
	printv(f'Speaker configuration set to {setup}.')
	_speaker_table = numpy.loadtxt(fname=table_file, delimiter='\t', skiprows=1, converters={3:lambda s:float(s or 0),4:lambda s:float(s or 0)}) # lambdas provide default values of 0 if azi or ele are not in the file
	printv('Speaker table loaded.')
	if _calibration_file.exists():
		_calibration_filter = slab.Filter.load(_calibration_file)
		printv('Calibration filters loaded.')
	else: printv('Setup not calibrated.')

def set_variable(variable, value, proc='RX8s'):

	'''
	Set a variable on a processor to a value. Setting will silently fail if
	variable does not exist in the rcx file. The function will use SetTagVal
	or WriteTagV correctly, depending on whether len(value) == 1 or is > 1.
	proc can be 'RP2', 'RX81', 'RX82', 'RX8s', or "all", or the index of the device
	in _procs (0 = RP2, 1 = RX81, 2 = RX82), or a list of indices.
	'RX8s' sends the value to all RX8 processors.
	Example:
	set_variable('stimdur', 90, proc='RX8s')
	'''
	if isinstance(proc, str):
		if proc =="all":
			proc = [_procs._fields.index('RX81'),_procs._fields.index('RX82'),_procs._fields.index('RP2')]
		elif proc == 'RX8s':
			proc = [_procs._fields.index('RX81'),_procs._fields.index('RX82')]
		else:
			proc = [_procs._fields.index(proc)]

	for p in proc:
		if isinstance(value, (list, numpy.ndarray)):
			_procs[p]._oleobj_.InvokeTypes(15, 0x0, 1, (3, 0), ((8, 0), (3, 0), (0x2005, 0)), variable, 0, value)
			printv(f'Set {variable} on {_procs._fields[p]}.')
		else:
			_procs[p].SetTagVal(variable, value)
			printv(f'Set {variable} to {value} on {_procs._fields[p]}.')

def get_variable(variable=None, n_samples=1, proc='RX81'):
	'''
	Get the value of a variable from a processor. Returns None if variable
	does not exist in the rco file. proc can be 'RP2', 'RX81', 'RX82', or
	the index of the device in _procs (0 = RP2, 1 = RX81, 2 = RX82).
	Example:
	get_variable('playing', proc='RX81')
	'''
	if isinstance(proc, str):
		proc = _procs._fields.index(proc)
	if n_samples > 1:
		value = numpy.asarray(_procs[proc].ReadTagV(variable, 0, n_samples))
	else: value = _procs[proc].GetTagVal(variable)
	printv(f'Got {variable} from {_procs._fields[proc]}.')
	return value

def trigger(trig='zBusA', proc=None):
	'''
	Send a trigger. Options are SoftTrig numbers, "zBusA" or "zBusB".
	For using the software trigger a processor must be specified by name
	or index in _procs. Initialize the zBus befor sending zBus triggers.
	'''
	if isinstance(trig, (int, float)):
		if not proc: raise ValueError('Proc needs to be specified for SoftTrig!')
		if isinstance(proc, str):
			proc = _procs._fields.index(proc) # name to index
		_procs[proc].SoftTrg(trig)
		printv(f'SoftTrig {trig} sent to {_procs._fields[proc]}.')
	elif 'zbus' in trig.lower():
		if not _procs.ZBus:
			raise ValueError('ZBus needs to be initialized first!')
		if trig.lower() == "zbusa":
			_procs.ZBus.zBusTrigA(0, 0, 20)
			printv('zBusA trigger sent.')
		elif trig.lower() == "zbusb":
			_procs.ZBus.zBusTrigB(0, 0, 20)

	else:
		raise ValueError("Unknown trigger type! Must be 'soft', 'zBusA' or 'zBusB'!")

def wait_to_finish_playing(proc='RX8s', tagname="playback"):
	'''
	Busy wait as long as sound is played from the processors. The .rcx file must
	contain a tag (default name is playback) that has the value 1 while sound is
	being played and 0 otherwise.
	'''
	if proc == 'RX8s':
		proc = ['RX81','RX82']
	elif proc == 'all':
		proc = ['RX81','RX82','RP2']
	else: proc = [proc]
	printv(f'Waiting for {tagname} on {proc}.')
	while any(get_variable(variable=tagname, n_samples=1, proc=processor) for processor in proc):
		time.sleep(0.01)
	printv('Done waiting.')


def get_speaker_from_direction(azimuth=0, elevation=0):
	'''
	Returns the speaker, channel, and RX8 index that the speaker
	at a given azimuth and elevation is attached to.
	'''
	row = int(numpy.argwhere(numpy.logical_and(_speaker_table[:,3]==azimuth, _speaker_table[:,4]==elevation)))
	return _speaker_table[row,0:3] # returns speaker, channel, and RX8 index


def speaker_from_number(speaker):
	'''
	Returns the channel, RX8 index, azimuth, and elevation
	that the speaker with a given number (1-48) is attached to.
	'''
	row = int(numpy.argwhere(_speaker_table[:,0]==speaker))
	channel = int(_speaker_table[row,1])
	rx8 = int(_speaker_table[row,2])
	azimuth = int(_speaker_table[row,3])
	elevation = int(_speaker_table[row,4])

	return channel, rx8, azimuth, elevation

def set_signal_and_speaker(signal=None, speaker=0, apply_calibration=True):
	'''
	Upload a signal to the correct RX8 and channel (channel on the other RX8 set to -1).
	If apply_calibration=True, apply the speaker's inverse filter before upoading.
	'speaker' can be a speaker number (1-48) or a tuple (azimuth, elevation).
	'''
	if isinstance(speaker, tuple):
		speaker, channel, proc = speaker_from_direction(azimuth=speaker[0], elevation=speaker[1])
	else:
		channel, proc, azi, ele = speaker_from_number(speaker)
	if apply_calibration:
		if not _calibration_file.exists():
			raise FileNotFoundError('No calibration file found. Please calibrate the speaker setup.')
		printv('Applying calibration.')
		signal = _calibration_filter.channel(speaker).apply(signal)
	proc_indices = set([1,2])
	other_procs = proc_indices.remove(proc)
	set_variable(variable='chan', value=channel, proc=proc)
	for other in other_procs:
		set_variable(variable='chan', value=-1, proc=other)

def get_headpose(n_images=10):

	if camera._cam is None:
		print("ERROR! Camera has to be initialized!")
	x,y,z = camera.get_headpose(n_images)
	return x,y,z

def printv(*args, **kwargs):
	if _verbose: print(*args, **kwargs)

def get_recording_delay(distance=1.6, samplerate=48828.125, da_delay=None, ad_delay=None):
	"""
	Calculate the delay it takes for played sound to be recorded. Depends on
	the distance of the microphone from the speaker and on the digital-to-analog
	and analog-to-digital conversion delays of the devices.
	"""
	n_sound_traveling = int(distance/343*samplerate)
	if da_delay:
		if da_delay=="RX8":
			n_da = 24
		elif da_delay=="RP2":
			n_da = 30
		else:
			raise ValueError("Input %s not understood!" %(da_delay))
	else: n_da = 0
	if ad_delay:
		if ad_delay=="RX8":
			n_ad = 47
		elif ad_delay=="RP2":
			n_ad = 65
		else:
			raise ValueError("Input %s not understood!" %(ad_delay))
	else: n_ad=0
	return n_sound_traveling+n_da+n_ad

# functions implementing complete procedures
def calibrate_speakers():
	'''
	Calibrate all speakers in the array by presenting a sound from each one,
	recording, computing inverse filters, and saving the calibration file.
	'''
	import datetime
	printv('Starting calibration.')
	slab.Signal.set_default_samplerate(48828.125)
	sig = slab.Sound.chirp(duration=10000, from_freq=100, to_freq=None, kind='quadratic')
	initialize_devices(RP2_file='calibration_RP2.rco', RX8_file='calibration_RX8.rco', connection='GB')
	input('Set up microphone. Press any key to start calibration...')
	set_variable(variable='signal', value=sig, proc='RX8s')
	recording = numpy.zeros((sig.nsamples, 48))
	for speaker in range(48):
		set_variable(variable='chan', value=speaker+1, proc='RX8s')
		for i in range(10):
			trigger() # zBusA by default
			wait_to_finish_playing()
			if i == 0: # first iteration
				rec = get_variable(variable='recording', proc='RP2')
			else:
				rec = rec + get_variable(variable='recording', proc='RP2')
		recording[:,speaker] = rec / 10 # averaging
	recording = slab.Sound(recording) # make a multi-channel sound object
	filt = slab.Filter.equalizing_filterbank(sig, recording) # make inverse filter
	# rename old filter file, if it exists, by appending current date
	if _calibration_file.exists():
		date = datetime.datetime.now().strftime("time: %Y-%m-%d-%H-%M-%S")
		rename_previous = _calibration_file.parent / Path(_calibration_file.stem + date + _calibration_file.suffix)
		_calibration_file.rename(rename_previous)
	filt.save(_calibration_file) # save filter file to 'calibration_arc.npy' or dome.
	printv('Calibration completed.')

def calibrate_headpose(n_repeat=5, bits=numpy.array([8,4,2,1]), pos=numpy.array([64.20, 47.08, 25.68, 0]), plot=True):
	""""
	Makes LEDs light up at the given postions. Subject has to align their head
	with the lit LED and push the button so a picture is taken and the head pose is
	determined. Then we can determine the coefficients of the linear regression for
	led position vs measured head position
	"""
	from sklearn.linear_model import LinearRegression
	from matplotlib import pyplot as plt
	rp2_file = _location.parents[0]/Path("example/button_response.rcx")
	rx8_file = _location.parents[0]/Path("example/to_bits.rcx")
	if not _speaker_config:
		set_speaker_config("arc")
	initialize_devices(RX81_file=rx8_file, RP2_file=rp2_file, ZBus=True, cam=True)
	trials = numpy.tile(bits, n_repeat)
	results=numpy.zeros([len(trials), 2])
	results[:,0] = trials
	for i, count in zip(trials,range(len(trials))):
		print("trial nr"+str(count))
		set_variable(variable="set_zero",value=False, proc="RX81")
		set_variable(variable="bitval",value=int(i), proc="RX81")
		tic = time.time()
		while not get_variable(variable="response", proc="RP2"):
			time.sleep(0.1) # wait untill button is pressed
		set_variable(variable="set_zero",value=True, proc="RX81")
		x,y,z = camera.get_headpose(n=5)
		if y is not None:
			results[count, 1]=y
			results[count, 0]=pos[numpy.where(bits==i)[0][0]]

	linear_regressor = LinearRegression()
	linear_regressor.fit(results[:,0].reshape(-1,1), results[:,1].reshape(-1,1))
	pred = linear_regressor.predict(results[:,0].reshape(-1,1))

	if plot:
		plt.scatter(results[:,0].reshape(-1,1), results[:,1].reshape(-1,1))
		plt.plot(results[:,0].reshape(-1,1), pred)
		plt.show()

	return results, linear_regressor