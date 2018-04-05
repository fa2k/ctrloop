import subprocess
import re
import sys
import serial

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


WATER_NTC_TARGET = 185
FAN_MIN = 102
FAN_FAC = (122 - 102) / (WATER_NTC_TARGET - 175)
COMP_TGT_TEMP = [70, 44, 72]
COMP_CRITFAN_TEMP = [70, 60, 88]
PUMP_MIN = 102
PUMP_FAC = 2

def loop():
    with serial.Serial('/dev/ttyUSB0', timeout=3) as ser:
        i=0
        while True:
            while ser.read() != b'!':
                pass
            water_ntc = int.from_bytes(ser.read(2), byteorder='big')
            # 192
            pc_temps = get_temps()
            ser.write(b'F')
            pump = min(sum(
                    int(max(0, (pct - ctt) * PUMP_FAC))
                    for pct, ctt in zip(pc_temps, COMP_TGT_TEMP)
                    ) + PUMP_MIN, 255)
            fan = max(WATER_NTC_TARGET - water_ntc, 0)*FAN_FAC + FAN_MIN
            fan += sum(
                    int(max(0, (pct - cct) * PUMP_FAC))
                    for pct, cct in zip(pc_temps, COMP_CRITFAN_TEMP)
                    )
            fan = int(min(fan, 255))
            ser.write(bytes([fan, pump]))
            if i % 10000 == 0:
                print("W:", water_ntc, "P:", pc_temps, "F:", fan, "U:", pump)
                sys.stdout.flush()
            i += 1
loop()

