import subprocess
import re
import sys
import serial

SERIAL_DEVICE = '/dev/ttyUSB0'
if (len(sys.argv) > 1 and sys.argv[1] == "debug"):
    REPORT_PER = 1
else:
    REPORT_PER = 100

SENSORS = ["coretemp.temp1"]

def get_nvidia_temp():
    data = subprocess.check_output(
            ['nvidia-smi', '-q', '-d', 'temperature']).decode('utf-8')
    for line in data.splitlines():
        m = re.match(r" *GPU Current Temp *: (\d+) ", line)
        if m:
            return int(m.group(1))
    else:
        raise RuntimeError("No temperature info")


def get_temps():
    data = subprocess.check_output(['/home/fa2k/git/ctrloop/gettemp/gettemp'] + SENSORS).decode('utf-8')
    try:
        cpu,  = [float(d) for d in data.splitlines()]
    except:
        cpu, = 80, 99
    try:
        nvi = get_nvidia_temp()
    except:
        nvi = 80
    return [cpu, nvi]


def clip_point(val, lowclip, highclip):
    if lowclip is not None:
        val = max(lowclip, val)
    if highclip is not None:
        val = min(highclip, val)
    return val


class PidLoop(object):

    n_deriv_smooth = 4

    def __init__(self, prop, inte, deri, intlowclip=None, inthighclip=None, n_deriv=30):
        self.prop = prop
        self.inte = inte
        self.deri = deri
        self.intlowclip = intlowclip
        self.inthighclip = inthighclip
        self.n_deriv = n_deriv
        #self.last_difs = []
        self.last_dif = None
        self.integral = 0

    def next(self, dif):
        self.integral = clip_point(self.integral + dif, 
                self.intlowclip / self.inte,
                self.inthighclip / self.inte)
        # Simple derivative code -- useless & ignored
        if self.last_dif is not None:
            deriv = dif - self.last_dif
        else:
            deriv = 0.0
        self.last_dif = dif
        # -- Derivative code : doesn't do much to help --
        #self.last_difs = [dif] + self.last_difs[:self.n_deriv-1]
        # Approximate the derivative over multiple time points, to even
        # out jitter and to measure derivatives of < 1 unit per time point.
        # Find slope of a straight line through the point n_deriv ago and
        # the current point. Because of the large constant factor, we also
        # do smoothing over dif values to keep it smooth.
        #if len(self.last_difs) == self.n_deriv:
        #    start = sum(self.last_difs[-self.n_deriv_smooth-1:-1]) / self.n_deriv_smooth
        #    start = sum(self.last_difs[:self.n_deriv_smooth]) / self.n_deriv_smooth
        #    deriv = (dif - start) / self.n_deriv
        #    if self.deri:
        #        print("derivative:", deriv)
        #else:
        #    deriv = 0
        return self.prop*dif + self.inte*self.integral + self.deri*deriv

class ExcludeRange:
    def __init__(self, low, high):
        self.low = low
        self.high = high
        self.current = None

    def transform(self, value):
        if (self.current == "high" and value > self.low) or value > self.high:
            self.current = "high"
            return max(self.high, value)
        else:
            self.current = "low"
            return min(self.low, value)


# Pump min spec = 20 % (51/255)
PUMP_MIN = 80
FAN_MIN = 64

#WATER_NTC_SETPOINT = 193
WATER_NTC_SETPOINT = 189
fan_pid = PidLoop(
        prop=13.0,
        inte=0.3,
        deri=0.0,
        intlowclip=0,
        inthighclip=257 - FAN_MIN
        )

COMPONENT_SET_TEMP = [68, 52]
pump_pid = PidLoop(
        prop=4.0,
        inte=0.05,
        deri=0.0,
        intlowclip=0,
        inthighclip=257 - PUMP_MIN
        )
pump_tf = ExcludeRange(120, 200)

N_WATER_MEDIAN = 4

# Speed up pump (minimum) when water temp is getting close to set point,
# to reduce lag in the system when regulating
PUMP_MIN_TEPID = 201
NTC_UNITS_PUMP_HAX = 5

def loop():
    with serial.Serial(SERIAL_DEVICE, timeout=3) as ser:
        i=0
        temp_int = 0.0
        temp_last = None
        water_int = 0.0
        water_last = None
        water_readings = [WATER_NTC_SETPOINT] * N_WATER_MEDIAN
        pump_hax_hyst = 0
        while True:
            while ser.read() != b'!':
                pass

            water_ntc = int.from_bytes(ser.read(2), byteorder='big')
            water_readings = [water_ntc] + water_readings[:-1]
            median_water_ntc = sum(
                    sorted(water_readings)[N_WATER_MEDIAN//2-1:N_WATER_MEDIAN//2+1]
                ) / 2
            pc_temps = get_temps()
            if median_water_ntc > 900:
                median_water_ntc = 0 # in case of broken connection
            water_diff = WATER_NTC_SETPOINT - median_water_ntc
            fan = fan_pid.next(water_diff)
            fan = int(min(max(fan, 0) + FAN_MIN, 255))

            temp_max_diff = max(
                    pct - ctt
                    for pct, ctt in zip(pc_temps, COMPONENT_SET_TEMP)
                    )
            pump = int(min(255, PUMP_MIN + max(0, pump_pid.next(temp_max_diff))))
            if water_diff >= -NTC_UNITS_PUMP_HAX - pump_hax_hyst: 
                pump = max(pump, PUMP_MIN_TEPID)
                pump_hax_hyst = 3
            else:
                pump_hax_hyst = 0
            pump = pump_tf.transform(pump)
            ser.write(b'F' + bytes([fan, pump]))
            if i % REPORT_PER == 0:
                print("W:", water_ntc, "T:", [int(t) for t in pc_temps],
                        "F:", fan, "P:", pump)
                sys.stdout.flush()
            i += 1
loop()

