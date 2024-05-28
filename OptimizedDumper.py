import datetime
import os
import re
from enum import IntEnum

import pytz
import serial


def get_tz_naive_datetime(tz_aware_datetime: datetime) -> datetime:
    return tz_aware_datetime.replace(tzinfo=None)


def _now(self):
    return get_tz_naive_datetime(datetime.datetime.now(tz=pytz.timezone("Australia/Sydney")))


class Params():
    serial_port = 'COM4'
    serial_speed = 115200

    block_size = 0x1000  # max_buffer (HydraBus limitation)
    spi = 1
    polarity = 0
    clock_phase = 0

    SPI_SPEED_TABLE = {
        1: {
            "320k": 0b01100000,
            "650k": 0b01100001,
            "1.31m": 0b01100010,
            "2.62m": 0b01100011,
            "5.25m": 0b01100100,
            "10.5m": 0b01100101,
            "21m": 0b01100110,
            "42m": 0b01100111,
        },
        0: {
            "160k": 0b01100000,
            "320k": 0b01100001,
            "650k": 0b01100010,
            "1.31m": 0b01100011,
            "2.62m": 0b01100100,
            "5.25m": 0b01100101,
            "10.5m": 0b01100110,
            "21m": 0b01100111,
        }
    }

    SPI_speed = 0b01100110


class ChipType(IntEnum):
    Atmega328p = 1

    def __str__(self):
        return ' '.join(re.findall('[A-Z][^A-Z]*', self.name))

    def __int__(self):
        return self.value

    def __repr__(self):
        return self.name


def check_result(result, expected, error_str):
    try:
        assert expected in result, f'{error_str}: expected={expected} != result={result}'
    except TypeError as type_error:
        print(f"Type error: {type_error}")
        print(f"Expected type: {type(expected)} | {expected = }")
        print(f"Result type: {type(result)} | {result = }")
        raise type_error


class SPIHydra:
    def __init__(self, port: str, baudrate: int, spi_device_select: int):
        self.params = Params()
        self.params.serial_port = port
        self.params.serial_speed = baudrate

        if spi_device_select not in [1, 2]:
            raise ValueError(f"SPI device number must be 1 or 2")
        self.params.spi = 1 if spi_device_select == 1 else 0  # https://pyhydrabus.readthedocs.io/en/latest/pyHydrabus.html#pyHydrabus.spi.SPI.device
        self.params.SPI_speed = Params.SPI_SPEED_TABLE[self.params.spi]["2.62m"]

        self.serial = None

    def __enter__(self):
        self.serial = serial.Serial(self.params.serial_port, self.params.serial_speed)

        # Switching HydraBus to binary mode
        for _ in range(20):
            self.serial.write(b'\x00')
        check_result(expected=b"BBIO1", result=self.serial.read(5), error_str='Could not switch into binary mode!')

        self.serial.reset_input_buffer()

        # Switching to SPI mode
        self.write_bytes(0b00000001)
        check_result(expected=b"SPI1", result=self.serial.read(4), error_str='Could not switch to SPI mode')

        # Configuring SPI
        cfg = 0b10000000 | self.params.polarity << 3 | self.params.clock_phase << 2 | self.params.spi
        self.write_bytes(cfg)  # polarity => 0, phase => 0, SPI1
        check_result(expected=b'\x01', result=self.serial.read(1), error_str='Could not setup SPI port!')

        # Setting up SPI speed
        self.write_bytes(self.params.SPI_speed)
        check_result(expected=b'\x01', result=self.serial.read(1), error_str='Could not setup SPI speed!')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Switch HydraBus back to terminal mode
        self.serial.write(b'\x00')
        self.serial.write(b'\x0F')

    def write_bytes(self, data):
        if not isinstance(data, list) and not isinstance(data, bytes):
            data = [data]
        self.serial.write(data)

    def read(self, num):
        return self.serial.read(num)

    def cs_high(self):
        self.write_bytes(0b00000011)
        check_result(expected=b'\x01', result=self.serial.read(1), error_str='Cannot switch CS to on!')

    def cs_low(self):
        self.write_bytes(0b00000010)
        check_result(expected=b'\x01', result=self.serial.read(1), error_str='Cannot switch CS to off!')


class HydraBusSPIFlashDumper:
    def __init__(self, port: str, baudrate: int, spi_device_select: int, chip: ChipType):
        implemented_chips = [ChipType.Atmega328p]
        self.chip = chip
        if self.chip not in implemented_chips:
            raise NotImplementedError(f"Chip {self.chip} is not implemented yet")

        self.hydra = SPIHydra(port, baudrate, spi_device_select)
        self.chip = chip

        self.serial_print_increment = 0x100

    def dump_flash(self, output_file: str):
        if self.chip == ChipType.Atmega328p:
            with self.hydra as hydra:
                # -------
                hydra.cs_low()
                print("Chip select is low")

                print("Getting Atmega manufacturer id ...")

                # Enable programming mode
                # send 4 bytes and read 4 bytes back
                hydra.write_bytes([0b00000101, 0x00, 0x04, 0x00, 0x04])
                # send RDID command
                command = [0xAC, 0x53, 0x00, 0x00]
                hydra.write_bytes(command)
                check_result(expected=b'\x01', result=hydra.read(1), error_str='Error occurred while enabling the programming mode!')
                reply: bytes = hydra.read(4)
                print(f"Programming mode enabled: {reply = }")

                # Getting chip id 1
                # send 3 bytes and read 1 byte back
                hydra.write_bytes([0b00000101, 0x00, 0x03, 0x00, 0x01])
                # send RDID command
                command = [0x30, 0x00, 0x00]
                hydra.write_bytes(command)
                check_result(expected=b'\x01', result=hydra.read(1), error_str='Error occurred while enabling the programming mode!')
                reply: bytes = hydra.read(1)
                expected_reply = b'\x1E'
                try:
                    check_result(expected=expected_reply, result=reply, error_str='The atmega328p chip ID 1 over SPI, was not the expected value!')
                    print(f"Chip ID 1 confirmed")
                except AssertionError as e:
                    print(f"Error: {e}")
                    raise e

                # Getting chip id 2
                hydra.write_bytes([0b00000101, 0x00, 0x03, 0x00, 0x01])
                # send RDID command
                command = [0x30, 0x00, 0x01]
                hydra.write_bytes(command)
                check_result(expected=b'\x01', result=hydra.read(1), error_str='Error occurred while enabling the programming mode!')
                reply: bytes = hydra.read(1)
                expected_reply = b'\x95'
                try:
                    check_result(expected=expected_reply, result=reply, error_str='The atmega328p chip ID 2 over SPI, was not the expected value!')
                    print(f"Chip ID 2 confirmed")
                except AssertionError as e:
                    print(f"Error: {e}")
                    raise e

                # Getting chip id 3
                hydra.write_bytes([0b00000101, 0x00, 0x03, 0x00, 0x01])
                # send RDID command
                command = [0x30, 0x00, 0x02]
                hydra.write_bytes(command)
                check_result(expected=b'\x01', result=hydra.read(1), error_str='Error occurred while enabling the programming mode!')
                reply: bytes = hydra.read(1)
                expected_reply = b'\x0F'
                try:
                    check_result(expected=expected_reply, result=reply, error_str='The atmega328p chip ID 3 over SPI, was not the expected value!')
                    print(f"Chip ID 3 confirmed")
                except AssertionError as e:
                    print(f"Error: {e}")
                    raise e

                def read_atmega_bytes(memory_address: int) -> tuple[bytes, bytes]:
                    """Using the entire chain, reads from an Atmega328p memory address the data and returns it as a tuple of low byte and high byte"""
                    address_as_hex_str: str = f"{memory_address:04X}"
                    segment: int = int(address_as_hex_str[:2], 16)
                    offset: int = int(address_as_hex_str[2:], 16)

                    hydra.write_bytes([0b00000101, 0x00, 0x03, 0x00, 0x01])
                    low_byte_command = [0x20, segment, offset]
                    hydra.write_bytes(low_byte_command)
                    check_result(expected=b'\x01', result=hydra.read(1), error_str=f'Error occurred while reading data from Atmega328p 0x{address_as_hex_str} memory address!')
                    l_byte: bytes = hydra.read(1)

                    hydra.write_bytes([0b00000101, 0x00, 0x03, 0x00, 0x01])
                    high_byte_command = [0x28, segment, offset]
                    hydra.write_bytes(high_byte_command)
                    check_result(expected=b'\x01', result=hydra.read(1), error_str=f'Error occurred while reading data from Atmega328p 0x{address_as_hex_str} memory address!')
                    h_byte: bytes = hydra.read(1)

                    return l_byte, h_byte

                with open(output_file, 'wb') as binary_file:
                    print(f"Dumping flash to {output_file} ...")
                    for mem_address in range(0, 16384):
                        if mem_address % self.serial_print_increment == 0:
                            print(f"Reading memory address 0x{mem_address:04X}")
                        low_byte, high_byte = read_atmega_bytes(mem_address)
                        binary_file.write(low_byte)
                        binary_file.write(high_byte)
                    print(f"Flash dumped to {output_file} ...")

                hydra.cs_high()
                print("Chip select is high")


if __name__ == '__main__':
    dump_folder = os.path.join(os.path.dirname(__file__), "dump")
    if not os.path.exists(dump_folder):
        os.makedirs(dump_folder, exist_ok=True)
    binary_dump = os.path.join(dump_folder, 'atmega328_flash_dump.bin')

    dumper = HydraBusSPIFlashDumper(port="COM4", baudrate=115200, spi_device_select=2, chip=ChipType.Atmega328p)
    dumper.dump_flash(binary_dump)
