import os.path
import time

import serial


def run_serial_cmds():
    # Configure the serial port
    port = 'COM4'
    baudrate = 115200

    # Commands to send
    commands = [
        'help\r\n',
        'spi\r\n',
        'device 2\r\n',
        'frequency 2620000\r\n',
        '[ 0xAC 0x53 0x00 0x00 hd:4\r\n',
        '0x30 0x00 0x00 hd:1\r\n',
        '0x30 0x00 0x01 hd:1\r\n',
        '0x30 0x00 0x02 hd:1\r\n',
    ]

    # File to store the terminal reply
    dump_folder = os.path.join(os.path.dirname(__file__), "out")
    if not os.path.exists(dump_folder):
        os.makedirs(dump_folder, exist_ok=True)
    output_file = os.path.join(dump_folder, 'terminal_traffic.log')
    binary_dump = os.path.join(dump_folder, 'atmega328_flash_dump.bin')

    try:
        # Open the serial port
        with serial.Serial(port, baudrate, timeout=1) as ser:
            # Give the serial connection a second to initialize
            time.sleep(0.5)

            def read_byte(address: int, low_byte: bool) -> tuple[str, str, bytes | None]:
                address_as_hex_str: str = f"{mem_address:04X}"
                segment: str = address_as_hex_str[:2]
                offset: str = address_as_hex_str[2:]
                str_command = f"0x20 0x{segment} 0x{offset} hd:1\r\n" if low_byte else f"0x28 0x{segment} 0x{offset} hd:1\r\n"
                ser.write(str_command.encode())
                time.sleep(0.5)
                received_reply = ser.read(ser.in_waiting).decode()

                if "Invalid command." in reply:
                    return str_command, received_reply, None
                line_3 = received_reply.splitlines()[2][:2]
                byte_from_reply = bytes.fromhex(line_3)
                return str_command, received_reply, byte_from_reply

                # Open the output log_file

            with open(output_file, 'w') as log_file:
                with open(binary_dump, 'wb') as binary_file:
                    for command in commands:
                        # Write the command to the serial port
                        ser.write(command.encode())
                        # Wait for the reply
                        time.sleep(0.5)
                        # Read the reply from the serial port
                        reply = ser.read(ser.in_waiting).decode()
                        # Write the reply to the log_file
                        log_file.write(f"Command >> {command.strip()}\n")
                        print(f"Command: {command.strip()}\n")
                        log_file.write(f"Reply   << {reply}\n")
                        print(f"Reply: {reply}\n")

                    for mem_address in range(0, 16384):
                        comm, repl, byte = read_byte(mem_address, True)
                        log_file.write(f"Command >> {comm.strip()}\n")
                        print(f"Command: {comm.strip()}\n")
                        log_file.write(f"Reply   << {repl}\n")
                        print(f"Reply: {repl}\n")
                        binary_file.write(byte)

                        comm, repl, byte = read_byte(mem_address, False)
                        log_file.write(f"Command >> {comm.strip()}\n")
                        print(f"Command: {comm.strip()}\n")
                        log_file.write(f"Reply   << {repl}\n")
                        print(f"Reply: {repl}\n")
                        binary_file.write(byte)

    except serial.SerialException as e:
        print(f"Error: {e}")


if __name__ == '__main__':
    run_serial_cmds()
