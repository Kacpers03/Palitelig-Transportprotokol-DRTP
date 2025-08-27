import socket
import time
import argparse
import struct

# Definnerer headerformatet og størrelsen på headere
HEADER_FORMAT = "!HHH"  # Dette er headerformat
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # Størrelsen på headeren

# Konstanter som representerer flaggene i headeren
SYN_FLAG = 0b1000  # SYN-flagget indikerer en forespørsel om å etablere en forbindelse
ACK_FLAG = 0b0100  # ACK-flagget indikerer en bekreftelse på mottak av data
FIN_FLAG = 0b0010  # FIN-flagget indikerer en forespørsel om å avslutte forbindelsen

def create_packet(seq_num, ack_num, flags, data=b''): 
    # Funksjonen oppretter en pakke med gitt sekvensnummer, bekreftelsesnummer, flagg og valgfri data.
    # Argumenter:
    #   - seq_num: Sekvensnummeret til pakken
    #   - ack_num: Bekreftelsesnummeret til pakken
    #   - flags: Flaggene som skal settes i headeren
    #   - data: Valgfri data som skal inkluderes i pakken 
    # Returnerer: Pakken med header og data
    header = struct.pack(HEADER_FORMAT, seq_num, ack_num, flags)
    return header + data

def get_header(packet):
    # Funksjonen henter ut headeren fra en gitt pakke.
    # Argument:
    #   - packet: Pakken som headeren skal ekstraheres fra
    # Returnerer: Headerinformasjon (sekvensnummer, bekreftelsesnummer, flagg)
    return struct.unpack(HEADER_FORMAT, packet[:HEADER_SIZE])

def send_packet(sock, packet, address):
    # Funksjonen sender en gitt pakke til en bestemt adresse ved hjelp av en gitt socket.
    # Argumenter:
    #   - sock: Socketen som skal brukes til å sende pakken
    #   - packet: Pakken som skal sendes
    #   - address: Måladressen hvor pakken skal sendes
    try:
        sock.sendto(packet, address)
    except socket.error as e:
        print(f"Error while sending packet: {e}")

def receive_packet(sock):
    # Funksjonen mottar en pakke ved hjelp av en gitt socket.
    # Argument:
    #   - sock: Socketen som skal brukes til å motta pakken
    # Returnerer:  Mottatt pakke og avsenderadresse
    try:
        packet, address = sock.recvfrom(1024)
        return packet, address
    except socket.timeout:
        return None, None
    except socket.error as e:
        print(f"Error while receiving packet: {e}")
        return None, None

def send_file(server_ip, server_port, filename, window_size, discard):
    # Funksjonen sender en fil til en server ved å etablere en forbindelse og overføre data.
    # Argumenter:
    #   - server_ip: IP-adressen til serveren
    #   - server_port: Portnummeret til serveren
    #   - filename: Navnet på filen som skal sendes
    #   - window_size: Størrelsen på skyvevinduet 
    #   - discard: Sekvensnummeret som skal forkastes for testing
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client_socket.settimeout(0.5)  # Setter en timeout for mottak av ACK-pakker

    try:
        with open(filename, 'rb') as file:
            data = file.read()  # Leser filens innhold
    except FileNotFoundError:
        print(f"File not found: {filename}")
        return

    seq_num = 1  # Sekvensnummeret til den første pakken
    ack_num = 0  # Bekreftelsesnummeret for mottatte pakker
    start_index = 0  # Startindeks for dataoverføringen i filen

    # Opprettelse av forbindelse
    print("Connection Establishment Phase:")
    print("Sending SYN packet...")
    syn_packet = create_packet(seq_num, ack_num, SYN_FLAG)  # Oppretter en SYN-pakke
    send_packet(client_socket, syn_packet, (server_ip, server_port))  # Sender SYN-pakken til serveren

    print("Waiting for SYN-ACK packet...")
    syn_ack_packet, _ = receive_packet(client_socket)  # Mottar SYN-ACK-pakken fra serveren
    if syn_ack_packet:
        _, _, flags = get_header(syn_ack_packet)
        if flags & (SYN_FLAG | ACK_FLAG):  # Sjekker om SYN-ACK-pakken er mottatt riktig
            print("SYN-ACK packet is received")
            print("Sending ACK packet...")
            ack_packet = create_packet(seq_num, ack_num + 1, ACK_FLAG)  # Oppretter en ACK-pakke
            send_packet(client_socket, ack_packet, (server_ip, server_port))  # Sender ACK-pakken til serveren
            print("ACK packet is sent")

            print("Connection Established.")
            print("\nData Transfer Phase:")
            # Fase for dataoverføring
            while start_index < len(data):
                try:
                    ack_packet, _ = receive_packet(client_socket)  # Mottar ACK-pakken fra serveren
                    if ack_packet:
                        _, ack_received, _ = get_header(ack_packet)
                        print(f"{time.strftime('%H:%M:%S.%f')} -- ACK for packet = {ack_received} is received")
                        ack_num = ack_received
                    else:
                        print("Timeout while waiting for ACK... resending packet")
                except socket.timeout:
                    print("Timeout while waiting for ACK... resending packet")

                # Deler dataen i pakker med riktig størrelse basert på vindusstørrelsen
                end_index = min(start_index + window_size * 198, len(data))  
                packet_data = data[start_index:end_index]
                packet = create_packet(seq_num, ack_num, 0, packet_data)  # Oppretter en data-pakke
                print(f"{time.strftime('%H:%M:%S.%f')} -- packet with seq = {seq_num} is sent, sliding window = {{{', '.join(map(str, range(max(1, seq_num - window_size), seq_num + 1)))}}}")
                send_packet(client_socket, packet, (server_ip, server_port))  # Sender data-pakken til serveren
                start_index = end_index
                seq_num += 1

            print("\nData Transfer Finished.")
            print("\nConnection Teardown Phase:")
            # Fase for nedleggelse av forbindelsen
            fin_packet = create_packet(seq_num, ack_num, FIN_FLAG)  # Oppretter en FIN-pakke
            send_packet(client_socket, fin_packet, (server_ip, server_port))  # Sender FIN-pakken til serveren

            print("FIN packet is sent")
            fin_ack_packet, _ = receive_packet(client_socket)  # Mottar FIN-ACK-pakken fra serveren
            if fin_ack_packet:
                _, _, flags = get_header(fin_ack_packet)
                if flags & (FIN_FLAG | ACK_FLAG):  # Sjekker om FIN-ACK-pakken er mottatt riktig
                    print("FIN ACK packet is received")

            print("Connection Teardown Completed.")
        else:
            print("Unexpected packet received during connection establishment.")
    else:
        print("Connection failed: No response from server.")

    client_socket.close()  # Lukker socketen etter at forbindelsen er nedlagt

def receive_file(server_ip, server_port, window_size, discard):
    # Funksjonen mottar en fil fra en klient ved å etablere forbindelse og motta data.
    # Argumenter:
    #   - server_ip: IP-adressen til serveren
    #   - server_port: Portnummeret til serveren
    #   - window_size: Størrelsen på skyvevinduet 
    #   - discard: Sekvensnummeret som skal forkastes for testing
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((server_ip, server_port))  # Binder socketen til serverens IP-adresse og portnummer

    seq_num = 0  # Sekvensnummeret til den første pakken
    ack_num = 0  # Bekreftelsesnummeret for mottatte pakker
    received_data = bytearray()  # Buffer for å samle mottatte data
    start_time = None  # Tidspunktet da dataoverføringen starter
    total_data_received = 0  # Total mengde mottatte data i byte

    print("Waiting for connection...")
    # Fase for opprettelse av forbindelse
    while True:
        packet, client_address = receive_packet(server_socket)  # Mottar pakken fra klienten
        if packet is None:
            continue

        if start_time is None:
            start_time = time.time()  # Starter tid når den første pakken mottas
        seq_num, ack_num, flags = get_header(packet)

        if flags & SYN_FLAG:  # Sjekker om det mottatte flagget er SYN
            print("SYN packet is received")
            print("Sending SYN-ACK packet...")
            syn_ack_packet = create_packet(seq_num, ack_num, SYN_FLAG | ACK_FLAG)  # Oppretter en SYN-ACK-pakke
            send_packet(server_socket, syn_ack_packet, client_address)  # Sender SYN-ACK-pakken til klienten
            print("SYN-ACK packet is sent")

        elif flags & ACK_FLAG:  # Sjekker om det mottatte flagget er ACK
            print("ACK packet is received")
            print("Connection established")
            break

    #Dataoverføringfase 
    while True:
        packet, client_address = receive_packet(server_socket)  # Mottar pakken fra klienten
        if packet is None:
            continue

        seq_num, ack_num, flags = get_header(packet)
        if flags & FIN_FLAG:  # Sjekker om det mottatte flagget er FIN
            print("FIN packet is received")
            fin_ack_packet = create_packet(seq_num, ack_num, FIN_FLAG | ACK_FLAG)  # Oppretter en FIN-ACK-pakke
            send_packet(server_socket, fin_ack_packet, client_address)  # Sender FIN-ACK-pakken til klienten
            print("FIN ACK packet is sent")
            break

        if seq_num == ack_num + 1:
            received_data.extend(packet[HEADER_SIZE:])  # Legger til dataen fra den mottatte pakken 
            ack_num = seq_num
            print(f"{time.strftime('%H:%M:%S.%f')} -- packet {seq_num} is received")
            ack_packet = create_packet(seq_num, ack_num, ACK_FLAG)  # Oppretter en ACK-pakke
            send_packet(server_socket, ack_packet, client_address)  # Sender ACK-pakken til klienten
            print(f"{time.strftime('%H:%M:%S.%f')} -- sending ack for the received {seq_num}")
            total_data_received += len(packet) - HEADER_SIZE  # Oppdaterer total mengde mottatte data

    elapsed_time = time.time() - start_time  # Beregner den totale overføringstiden
    throughput = (total_data_received * 8) / (elapsed_time * 1000000)  # Beregner overføringshastigheten i Mbps
    print(f"\nThe throughput is {throughput:.2f} Mbps")  # Skriver ut overføringshastigheten
    print("Connection Closes")  # Skriver ut at forbindelsen er lukket

if __name__ == "__main__":
    # Oppretter en argumentparser for å håndtere kommandolinjealternativer
    parser = argparse.ArgumentParser(description="DRTP File Transfer Application")
    parser.add_argument("-s", "--server", action="store_true", help="Enable server mode")
    parser.add_argument("-c", "--client", action="store_true", help="Enable client mode")
    parser.add_argument("-i", "--ip", help="IP address", required=True)  # IP-adressen til serveren eller klienten
    parser.add_argument("-p", "--port", type=int, help="Port number", required=True)  # Portnummeret for kommunikasjon
    parser.add_argument("-f", "--file", help="File to send (for client mode)")  # Filen som skal sendes (kun for klientmodus)
    parser.add_argument("-w", "--window", type=int, default=5, help="Sliding window size")  # Størrelsen på skyvevinduet 
    parser.add_argument("-d", "--discard", type=int, default=-1, help="Discard a specific sequence number for testing")  # Sekvensnummeret som skal forkastes for testing

    args = parser.parse_args()  

    if args.server:  
        receive_file(args.ip, args.port, args.window, args.discard)  # Start mottak av fil på serveren
    elif args.client:  # Hvis klientmodus er aktivert
        if not args.file:  # Hvis ingen fil er spesifisert for klientmodus
            print("File must be specified for client mode")  # Skriv ut feilmelding
        else:
            send_file(args.ip, args.port, args.file, args.window, args.discard)  # Start sending av fil fra klienten
    else:
        print("Invalid mode: -s for server or -c for client must be specified")  # Skriv ut feilmelding hvis hverken server- eller klientmodus er spesifisert
