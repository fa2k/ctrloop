import subprocess
import re
import sys
import serial

SERIAL_DEVICE = '/dev/ttyUSB0'

def get_nvidia_temps():
    data = subprocess.check_output(
            ['nvidia-smi', '-q', '-d', 'temperature']).decode('utf-8')
    for line in data.splitlines():
        m = re.match(r" *GPU Current Temp *: (\d+) ", line)
        if m:
            yield int(m.group(1))

def get_cpu_ati_temp():
    data = subprocess.check_output(['sensors']).decode('utf-8')
    cpu = False
    ati = False
    ati_maxval = 0
    cpu_maxval = 0
    for line in data.splitlines():
        if line.startswith('coretemp-'):
            cpu = True
            maxval = 0
        elif line.startswith('amdgpu-'):
            ati = True
            maxval = 0
        elif not line.strip():
            cpu = False
            ati = False
        else:
            m = re.match(r".*: *\+([\d.]+)", line)
            if m:
                if ati:
                    ati_maxval = max(ati_maxval, float(m.group(1)))
                if cpu:
                    cpu_maxval = max(cpu_maxval, float(m.group(1)))
    return [cpu_maxval, ati_maxval]


def get_temps():
    cpu, ati = get_cpu_ati_temp()
    nvi = next(iter(get_nvidia_temps()))
    return [cpu, nvi, ati]


def clip_point(val, lowclip, highclip):
    if lowclip is not None:
        val = max(lowclip, val)
    if highclip is not None:
        val = min(highclip, val)
    return val


class PidLoop(object):
    def __init__(self, prop, inte, deri, intlowclip=None, inthighclip=None):
        self.prop = prop
        self.inte = inte
        self.deri = deri
        self.intlowclip = intlowclip
        self.inthighclip = inthighclip
        self.last_dif = None
        self.integral = 0

    def next(self, dif):
        self.integral = clip_point(self.integral + dif, 
                self.intlowclip, self.inthighclip)
        if self.last_dif is not None:
            deriv = dif - self.last_dif
        else:
            deriv = 0
        self.last_dif = dif
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
FAN_MIN = 90

CF_FAC = 25

COMPONENT_CRITFAN_TEMP = [70, 60, 85] 
#WATER_NTC_SETPOINT = 193
WATER_NTC_SETPOINT = 188
fan_pid = PidLoop(
        prop=6.0,
        inte=0.08,
        deri=0.0,
        intlowclip=-100,
        inthighclip=2700)

COMPONENT_SET_TEMP = [70, 52, 77]
pump_pid = PidLoop(
        prop=4.0,
        inte=0.04,
        deri=0.0,
        intlowclip=-20,
        inthighclip=5000
        )
pump_tf = ExcludeRange(120, 200)

def loop():
    with serial.Serial(SERIAL_DEVICE, timeout=3) as ser:
        i=0
        temp_int = 0.0
        temp_last = None
        water_int = 0.0
        water_last = None
        while True:
            while ser.read() != b'!':
                pass

            water_ntc = int.from_bytes(ser.read(2), byteorder='big')
            pc_temps = get_temps()

            fan = fan_pid.next(WATER_NTC_SETPOINT - water_ntc)
            fan += sum(
                    int(max(0, (pct - cct) * CF_FAC))
                    for pct, cct in zip(pc_temps, COMPONENT_CRITFAN_TEMP)
                    )
            fan = int(min(max(fan, 0) + FAN_MIN, 255))

            temp_max_diff = max(
                    pct - ctt
                    for pct, ctt in zip(pc_temps, COMPONENT_SET_TEMP)
                    )
            pump = int(min(255, PUMP_MIN + max(0, pump_pid.next(temp_max_diff))))
            pump = pump_tf.transform(pump)
            ser.write(b'F' + bytes([fan, pump]))
            if i % 100 == 0:
                print("W:", water_ntc, "T:", [int(t) for t in pc_temps],
                        "F:", fan, "P:", pump)
                sys.stdout.flush()
            i += 1
loop()

