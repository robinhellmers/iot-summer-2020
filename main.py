from network import WLAN
import machine
from mqtt import MQTTClient
import json
from time import sleep
import pycom
import _thread



SOIL_MOISTURE_PIN = "P16"

WIFI_SSID = "SSID-to-be-filled-in-by-user"
WIFI_PASSWORD = "PASSWORD-to-be-filled-in-by-user"

UBIDOTS_BROKER_URL = "things.ubidots.com"
UBIDOTS_BROKER_PORT = 1883
UBIDOTS_TOKEN = "token-to-be-filled-in-by-user"
UBIDOTS_PASSWORD = ""
UBIDOTS_DEVICE_LABEL = "soil_moisture_sensor"

TIME_DELAY_MEASUREMENT = 5  # Delay in seconds between measurements
NUM_MEASUREMENTS = 100 # Number of measurements before setting new reference

TIMER_SLEEP = 1

# Difference in percentage of reference voltage to recognize as watered
SENSOR_THRESHOLD = 0.01 

WATER_INTERVAL_DAYS = 5
WATER_INTERVAL_HOURS = 12
WATER_INTERVAL_SECONDS = 30

# ADC
ADC_VOLTAGE_CALIBRATION = 1157 # mV

# Don't change
client = '' # Filled in in setup_server()
SENSOR_THRESHOLD = 0.9 # Per
status = 0 # 0 = idle, 1 = you watered, 2 = time to water
th_lock = _thread.allocate_lock() # Thread lock
rtc = machine.RTC() # Real-time clock for time measurement
voltage = 0
reference_voltage = 0


def setup_wifi():
    wlan = WLAN(mode=WLAN.STA) # Setup as station for use of existing network

    nets = wlan.scan()
    
    print("Scanning for networks...")
    for net in nets:
        if (net.ssid == WIFI_SSID):
            print("\nThe network", WIFI_SSID, "was found!")
            print("Establishing connection to network...")

            wlan.connect(net.ssid, auth=(net.sec, WIFI_PASSWORD), timeout=5000)

            while not wlan.isconnected():
                machine.idle() # Save power

            print("Successful network connection!\n")
            break

def connect_server():
    global client
    client = MQTTClient(client_id=UBIDOTS_DEVICE_LABEL,
                        server=UBIDOTS_BROKER_URL,
                        port=UBIDOTS_BROKER_PORT,
                        user=UBIDOTS_TOKEN,
                        password=UBIDOTS_PASSWORD)
    client.connect()

def send_data(reference_voltage, voltage, status):
    global client
    data_to_send = b'{"reference_voltage": %d, "voltage": %d, "status": %d}' % (reference_voltage, voltage, status)
    client.publish("/v1.6/devices/"+UBIDOTS_DEVICE_LABEL, data_to_send)

def blink_led(color, intensity, duration):
    if (intensity >= 0 and intensity <= 1):
        intensity = int(intensity*255)
        if (color == "R"):
            led_value = intensity << 16
        elif (color == "G"):
            led_value = intensity << 8
        elif (color == "B"):
            led_value = intensity
        elif (color == "W"):
            led_value = (intensity << 16) | (intensity << 8) | (intensity)
        elif (color == "RG" or color == "GR"):
            led_value = (intensity << 16) | (intensity << 8)
        elif (color == "RB" or color == "BR"):
            led_value = (intensity << 16) | (intensity)
        elif (color == "GB" or color == "BG"):
            led_value = (intensity << 8)  | (intensity)
        else:
            return
        
        pycom.rgbled(led_value)
        sleep(duration)
        pycom.rgbled(0)




def main():
    global th_lock, rtc, reference_voltage, voltage

    # Setup ADC for soil moisture sensor
    adc = machine.ADC(bits=12)
    adc.vref(ADC_VOLTAGE_CALIBRATION) # Calibration value from adc.vref_to_pin()
    analog_pin = adc.channel(pin=SOIL_MOISTURE_PIN)

    while 1:
        
        reference_voltage = analog_pin.voltage()
        
        for i in range(1, NUM_MEASUREMENTS + 1):
            print("*********Variable i = ",i)

            blink_led("W", 0.1, 0.1)
            
            voltage = analog_pin.voltage()

            if (i == 2 or i == 10):
                # Watered!
                print("Watered!")
                status = 1
                blink_led("G", 0.1, 5)
                with th_lock:
                    rtc.init((2020,1,1,0,0,0,0,0)) # Reset clock
                    send_data(reference_voltage, voltage, status)
                print("Sent data!")

            if (voltage/reference_voltage <= (1 - SENSOR_THRESHOLD)):
                status = 1 # The plants were watered
                blink_led("G", 0.1, 10)
                with th_lock:
                    rtc.init((2020,1,1,0,0,0,0,0)) # Reset clock
                    send_data(reference_voltage, voltage, status)
            
            sleep(TIME_DELAY_MEASUREMENT)

# Checks if the user specified time interval for watering has gone since watered
def time_since_watered_check():
    while 1:

        time = rtc.now()
        days = time[2]
        hours = time[3]

        if (days >= WATER_INTERVAL_DAYS):

            if (hours >= WATER_INTERVAL_HOURS):

                status = 2 # Time to water the plants

                with th_lock:
                    send_data(reference_voltage, voltage, status)
                    rtc.init((2020,1,1,0,0,0,0,0)) # Reset clock

        sleep(TIMER_SLEEP)


pycom.heartbeat(False)

setup_wifi()

connect_server()

with th_lock:
    rtc.init((2020,1,1,0,0,0,0,0))


_thread.start_new_thread(main, ())
_thread.start_new_thread(time_since_watered_check, ())




