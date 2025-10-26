#!/usr/bin/env python3

# ==================================================================================
# NTKFWinfo - python script for work with Novatek firmware binary files
# Show full FW info, allow extract/replace/uncompress/compress partitions, fix CRC
#
# Copyright © 2025 Dex9999(4pda.to) aka Dex aka EgorKin(GitHub, etc.)
# ==================================================================================

# MEMORY OPTIMIZED VERSION - Key improvements:
# 1. Streaming file operations instead of loading entire files into memory
# 2. Chunked reading/writing for large files
# 3. Efficient buffer management
# 4. Reduced redundant data copies
# 5. Generator-based CRC calculation

CURRENT_VERSION = '6.7-optimized'

import os, struct, sys, argparse, array
from datetime import datetime, timezone
import zlib
import lzma
import subprocess
import platform

# Chunk size for streaming operations (1MB)
CHUNK_SIZE = 1024 * 1024

in_file = ''
in_offset = 0
out_file = ''

part_startoffset = array.array('I')
part_endoffset = array.array('I')
part_size = array.array('I')
part_id = array.array('I')
part_type = []
part_crc = array.array('I')
part_crcCalc = array.array('I')

dtbpart_ID = []
dtbpart_name = []
dtbpart_filename = []

is_ARM64 = 0

# defines from uboot source code
uImage_os = {
    0 : 'Invalid OS',
    1 : 'OpenBSD',
    2 : 'NetBSD',
    3 : 'FreeBSD',
    4 : '4.4BSD',
    5 : 'LINUX',
    6 : 'SVR4',
    7 : 'Esix',
    8 : 'Solaris',
    9 : 'Irix',
    10: 'SCO',
    11: 'Dell',
    12: 'NCR',
    13: 'LynxOS',
    14: 'VxWorks',
    15: 'pSOS',
    16: 'QNX',
    17: 'Firmware',
    18: 'RTEMS',
    19: 'ARTOS',
    20: 'Unity OS',
    21: 'INTEGRITY',
    22: 'OSE',
    23: 'Plan 9',
    24: 'OpenRTOS',
    25: 'ARM Trusted Firmware',
    26: 'Trusted Execution Environment',
    27: 'RISC-V OpenSBI',
    28: 'EFI Firmware (e.g. GRUB2)'
}

uImage_arch = {
    0 : 'Invalid CPU',
    1 : 'Alpha',
    2 : 'ARM',
    3 : 'Intel x86',
    4 : 'IA64',
    5 : 'MIPS',
    6 : 'MIPS 64 Bit',
    7 : 'PowerPC',
    8 : 'IBM S390',
    9 : 'SuperH',
    10: 'Sparc',
    11: 'Sparc 64 Bit',
    12: 'M68K',
    13: 'Nios-32',
    14: 'MicroBlaze',
    15: 'Nios-II',
    16: 'Blackfin',
    17: 'AVR32',
    18: 'STMicroelectronics ST200',
    19: 'Sandbox architecture (test only)',
    20: 'ANDES Technology - NDS32',
    21: 'OpenRISC 1000',
    22: 'ARM64',
    23: 'Synopsys DesignWare ARC',
    24: 'AMD x86_64, Intel and Via',
    25: 'Xtensa',
    26: 'RISC-V'
}

uImage_imagetype = {
    0 : 'Invalid Image',
    1 : 'Standalone Program',
    2 : 'OS Kernel Image',
    3 : 'RAMDisk Image',
    4 : 'Multi-File Image',
    5 : 'Firmware Image',
    6 : 'Script file',
    7 : 'Filesystem Image (any type)',
    8 : 'Binary Flat Device Tree Blob',
    9 : 'Kirkwood Boot Image',
    10: 'Freescale IMXBoot Image'
}

uImage_compressiontype = {
    0 : 'No',
    1 : 'gzip',
    2 : 'bzip2',
    3 : 'lzma',
    4 : 'lzo',
    5 : 'lz4',
    6 : 'zstd'
}

embtypes = {
    0x00 : 'UNKNOWN',
    0x01 : 'UITRON',
    0x02 : 'ECOS',
    0x03 : 'UBOOT',
    0x04 : 'LINUX',
    0x05 : 'DSP',
    0x06 : 'PSTORE',
    0x07 : 'FAT',
    0x08 : 'EXFAT',
    0x09 : 'UBIFS',
    0x0A : 'RAMFS',
    0x0B : 'UENV'
}

compressAlgoTypes = {
    0x01 : 'RLE',
    0x02 : 'HUFFMAN',
    0x03 : 'RICE8',
    0x04 : 'RICE16',
    0x05 : 'RICE32',
    0x06 : 'RICE8S',
    0x07 : 'RICE16S',
    0x08 : 'RICE32S',
    0x09 : 'LZ',
    0x0A : 'SF',
    0x0B : 'LZMA',
    0x0C : 'ZLIB'
}


def ShowInfoBanner():
    print("===================================================================================")
    print("  \033[92mNTKFWinfo\033[0m - python script for work with Novatek firmware binary files. Ver. %s" % (CURRENT_VERSION))
    print("  Show full FW \033[93mi\033[0mnfo, allow e\033[93mx\033[0mtract/\033[93mr\033[0meplace/\033[93mu\033[0mncompress/\033[93mc\033[0mompress partitions, \033[93mfixCRC\033[0m")
    print("")
    print("  Copyright © 2025 \033[93mDex9999\033[0m(4pda.to) aka \033[93mDex\033[0m aka \033[93mEgorKin\033[0m(GitHub, etc.)")
    print("  If you like this project or use it with commercial purposes please donate some")
    print("  \033[93mBTC\033[0m to: \033[92m12q5kucN1nvWq4gn5V3WJ8LFS6mtxbymdj\033[0m")
    print("===================================================================================")


def get_args():
    global in_file
    global is_extract
    global is_uncompress
    global is_compress
    global is_silent
    global workdir

    p = argparse.ArgumentParser(add_help=True, description='')
    p.add_argument('-i',metavar='filename', nargs=1, help='input file')
    p.add_argument('-x',metavar=('partID', 'offset'), nargs='+', help='extract partition by ID with optional start offset or all partitions if partID set to "ALL"')
    p.add_argument('-r',metavar=('partID', 'offset', 'filename'), nargs=3, help='replace partition by ID with start offset using input file')
    p.add_argument('-u',metavar=('partID', 'offset'), type=int, nargs='+', help='uncompress partition by ID with optional start offset')
    p.add_argument('-c',metavar=('partID'), type=int, nargs=1, help='compress partition by ID to firmware input file and fixCRC')
    p.add_argument('-udtb',metavar=('DTB_filename', 'DTS_filename'), nargs='+', help='convert DTB to DTS file')
    p.add_argument('-cdtb',metavar=('DTS_filename', 'DTB_filename'), nargs='+', help='convert DTS to DTB file')
    p.add_argument('-fixCRC', action='store_true', help='fix CRC values for all possible partitions and whole FW file')
    p.add_argument('-silent', action='store_true', help='do not print messages, except errors')
    p.add_argument('-o',metavar='outputdir', nargs=1, help='set working dir')

    if len(sys.argv) < 3:
        ShowInfoBanner()
        p.print_help(sys.stderr)
        sys.exit(1)

    args=p.parse_args(sys.argv[1:])

    if args.o:
        workdir = args.o[0]
        if not os.path.exists(workdir):
            os.system('mkdir ' + '\"' + workdir + '\"')
    else:
        workdir = ''
    
    if args.x:
        if (args.x[0] == 'all') | (args.x[0] == 'ALL'):
            is_extract_all = 1
            is_extract_offset = 0
            is_extract = 0xFF
        else:
            is_extract_all = 0
            is_extract = int(args.x[0])
            if len(args.x) == 2:
                is_extract_offset = int(args.x[1])
            else:
                is_extract_offset = -1
    else:
        is_extract = -1
        is_extract_offset = -1
        is_extract_all = 0

    if args.r:
        is_replace = int(args.r[0])
        is_replace_offset = int(args.r[1])
        is_replace_file = str(args.r[2])
    else:
        is_replace = -1
        is_replace_offset = -1
        is_replace_file = ''

    if args.u:
        is_uncompress = args.u[0]
        if len(args.u) == 2:
            is_uncompress_offset = int(args.u[1])
        else:
            is_uncompress_offset = -1
    else:
        is_uncompress = -1
        is_uncompress_offset = -1

    if args.udtb:
        if len(args.udtb) == 2:
            uncompressDTB(args.udtb[0], args.udtb[1])
        else:
            uncompressDTB(args.udtb[0])
        exit(0)

    if args.cdtb:
        if len(args.cdtb) == 2:
            compressToDTB(args.cdtb[0], args.cdtb[1])
        else:
            compressToDTB(args.cdtb[0])
        exit(0)

    if args.c:
        is_compress = args.c[0]
    else:
        is_compress = -1

    if args.fixCRC:
        fixCRC_partID = 1
    else:
        fixCRC_partID = -1

    if args.silent:
        is_silent = 1
    else:
        is_silent = -1

    in_file=args.i[0]

    return (in_file, is_extract, is_extract_offset, is_extract_all, is_replace, is_replace_offset, is_replace_file, is_uncompress, is_uncompress_offset, is_compress, fixCRC_partID)


# OPTIMIZED: Streaming CRC calculation to avoid loading entire file into memory
def MemCheck_CalcCheckSum16Bit_Streaming(input_file, in_offset, uiLen, ignoreCRCoffset):
    """Calculate CRC using streaming to minimize memory usage"""
    uiSum = 0
    pos = 0
    
    with open(input_file, 'rb') as fin:
        fin.seek(in_offset, 0)
        bytes_remaining = uiLen
        
        while bytes_remaining > 0:
            chunk_size = min(CHUNK_SIZE, bytes_remaining)
            # Ensure chunk_size is even for 16-bit reading
            if chunk_size % 2 == 1 and bytes_remaining > 1:
                chunk_size -= 1
            
            fread = fin.read(chunk_size)
            if not fread:
                break
            
            num_words = len(fread) // 2
            for chunk in struct.unpack("<%sH" % num_words, fread[:num_words*2]):
                if pos*2 != ignoreCRCoffset:
                    uiSum += chunk + pos
                else:
                    uiSum += pos
                pos += 1
            
            bytes_remaining -= chunk_size
    
    uiSum = uiSum & 0xFFFF
    uiSum = (~uiSum & 0xFFFF) + 1
    return uiSum


# Keep original for compatibility, but redirect to streaming version
def MemCheck_CalcCheckSum16Bit(input_file, in_offset, uiLen, ignoreCRCoffset):
    return MemCheck_CalcCheckSum16Bit_Streaming(input_file, in_offset, uiLen, ignoreCRCoffset)


def compress_CKSM_UBI(part_nr, in2_file):
    global in_file, is_ARM64

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)
        FourCC = fin.read(4)

        if FourCC != b'CKSM':
            print('\033[91mNot CKSM partition, exit\033[0m')
            exit(0)

        fin.seek(part_startoffset[part_nr] + 0x40, 0)
        FourCC = fin.read(4)
        if FourCC != b'UBI#':
            print('\033[91mNot UBI# into CKSM partition, exit\033[0m')
            exit(0)

    if not os.path.exists(in2_file):
        print('\033[91m%s folder does not found, exit\033[0m' % in2_file)
        exit(0)

    # OPTIMIZED: Stream extraction instead of loading entire partition
    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr] + 0x40, 0)
        with open(in2_file + '/tempfile', 'wb') as fpartout:
            bytes_remaining = part_size[part_nr] - 0x40
            while bytes_remaining > 0:
                chunk_size = min(CHUNK_SIZE, bytes_remaining)
                chunk = fin.read(chunk_size)
                if not chunk:
                    break
                fpartout.write(chunk)
                bytes_remaining -= len(chunk)

    subprocess.run('rm -rf ' + '\"' + in2_file + '/tempdir' + '\"', shell=True)
    subprocess.check_output('ubireader_utils_info ' + '-o ' + '\"' + in2_file + '/tempdir' + '\"' + ' ./' + '\"' + in2_file + '/tempfile' + '\"', shell=True)
    subprocess.run('rm ' + '\"' + in2_file + '/tempfile' + '\"', shell=True)
    
    d = os.popen('(cd ' + '\"' + in2_file + '\"' + '&& find -maxdepth 1 -wholename "./*" -not -wholename "./temp*" -type d)').read()

    if not os.path.exists(in2_file + d[1:-1]):
        print('\033[91mNo input valid folder in %s found, exit\033[0m' % in2_file)
        exit(0)

    d = d[2:-1]

    subprocess.run('(cd ' + '\"' + in2_file + '/tempdir/tempfile/img-' + d + '\"' + ' && sed -i "/vol_flags = 0/d" img-' + d + '.ini)', shell=True)

    if (is_ARM64 == 1):
        if dtbpart_name[part_id[part_nr]][:6] == 'rootfs':
            subprocess.run('(cd ' + '\"' + in2_file + '/tempdir/tempfile/img-' + d + '\"' + ' && sed -i "s/-x lzo/-x favor_lzo/" create_ubi_img-' + d + '.sh)', shell=True)

    subprocess.run('(cd ' + '\"' + in2_file + '/tempdir/tempfile/img-' + d + '\"' + ' && sudo ./create_ubi_img-' + d + '.sh ../../../' + d + '/*)', shell=True)

    global is_silent
    is_silent = 1

    partition_replace(part_id[part_nr], 0x40, in2_file + '/tempdir/tempfile/img-' + d + '/img-' + d + '.ubi')

    subprocess.run('rm -rf ' + '\"' + in2_file + '/tempdir' + '\"', shell=True)

    is_silent = 0
    fixCRC(part_id[part_nr])


def compress_CKSM_BCL(part_nr, in2_file):
    global in_file

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)
        FourCC = fin.read(4)

        if FourCC != b'CKSM':
            print('\033[91mNot CKSM partition, exit\033[0m')
            exit(0)

        fin.seek(part_startoffset[part_nr] + 0x40, 0)
        FourCC = fin.read(4)
        if FourCC != b'BCL1':
            print('\033[91mNot BCL1 into CKSM partition, exit\033[0m')
            exit(0)

    if not os.path.isfile(in2_file):
        print('\033[91m%s file does not found, exit\033[0m' % in2_file)
        exit(0)

    BCL1_compress(part_nr, 0x40, in2_file)

    comp_filename = in2_file.replace('uncomp_partitionID', 'comp_partitionID')
    if not os.path.isfile(comp_filename):
        print('\033[91m%s compressed partition file does not found, exit\033[0m' % comp_filename)
        exit(0)
    
    global is_silent
    is_silent = 1

    partition_replace(part_id[part_nr], 0x40, comp_filename)

    subprocess.run('rm -rf ' + '\"' + comp_filename + '\"', shell=True)

    is_silent = 0
    fixCRC(part_id[part_nr])


def compress_CKSM_SPARSE(part_nr, in2_file):
    global in_file

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)
        FourCC = fin.read(4)

        if FourCC != b'CKSM':
            print('\033[91mNot CKSM partition, exit\033[0m')
            exit(0)

        fin.seek(part_startoffset[part_nr] + 0x40, 0)
        FourCC = fin.read(4)
        if struct.unpack('>I', FourCC)[0] != 0x3AFF26ED:
            print('\033[91mNot SPARSE into CKSM partition, exit\033[0m')
            exit(0)

    if not os.path.exists(in2_file):
        print('\033[91m%s folder does not found, exit\033[0m' % in2_file + '/mount')
        exit(0)

    if not os.path.isfile(in2_file + '/tempfile.ext4'):
        print('\033[91m%s file does not found, exit\033[0m' % in2_file + '/tempfile.ext4')
        exit(0)

    subprocess.run('umount -d -f ' + '\"' + in2_file + '/mount' + '\"', shell=True)
    subprocess.run('img2simg ' + '\"' + in2_file + '/tempfile.ext4' + '\"' + ' ' + '\"' + in2_file + '/tempSPARSEfile' + '\"', shell=True)

    global is_silent
    is_silent = 1

    partition_replace(part_id[part_nr], 0x40, in2_file + '/tempSPARSEfile')

    os.system('rm -rf ' + '\"' + in2_file + '\"')

    is_silent = 0
    fixCRC(part_id[part_nr])


def compress_BCL(part_nr, in2_file):
    global in_file
    global FW_BOOTLOADER

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)
        FourCC = fin.read(4)
        if FourCC != b'BCL1':
            print('\033[91mNot BCL1 partition, exit\033[0m')
            exit(0)

    if not os.path.isfile(in2_file):
        print('\033[91m%s file does not found, exit\033[0m' % in2_file)
        exit(0)

    BCL1_compress(part_nr, 0, in2_file)

    comp_filename = in2_file.replace('uncomp_partitionID', 'comp_partitionID')
    if not os.path.isfile(comp_filename):
        print('\033[91m%s compressed partition file does not found, exit\033[0m' % comp_filename)
        exit(0)

    global is_silent
    is_silent = 1

    partition_replace(part_id[part_nr], 0, comp_filename)

    subprocess.run('rm -rf ' + '\"' + comp_filename + '\"', shell=True)
    
    if FW_BOOTLOADER == 1:
        filesize = os.path.getsize(in_file)
        with open(in_file, 'r+b') as fin:
            fin.seek(0x24, 0)
            file_size_from_header = struct.unpack('<I', fin.read(4))[0]
            if file_size_from_header > filesize:
                fin.seek(0, 2)
                fin.write(b'\x00' * (file_size_from_header - filesize))
            elif filesize > file_size_from_header:
                print('\033[91mFatal error: New bootlader file size exeed initial limit\033[0m')
                exit(0)

    is_silent = 0
    fixCRC(part_id[part_nr])


def compress_FDT(part_nr, in2_file):
    global in_file
    
    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)
        FourCC = fin.read(4)
        if struct.unpack('>I', FourCC)[0] != 0xD00DFEED:
            print('\033[91mNot FDT(DTB) partition, exit\033[0m')
            exit(0)

    if not os.path.isfile(in2_file):
        print('\033[91m%s file does not found, exit\033[0m' % in2_file)
        exit(0)

    comp_filename = in2_file.replace('uncomp_partitionID', 'comp_partitionID')
    os.system('dtc -qq -I dts -O dtb ' + '\"' + in2_file + '\"' + ' -o ' + '\"' + comp_filename + '\"')

    if not os.path.isfile(comp_filename):
        print('\033[91m%s compressed partition file does not found, exit\033[0m' % comp_filename)
        exit(0)

    global is_silent
    is_silent = 1

    partition_replace(part_id[part_nr], 0, comp_filename)
    
    subprocess.run('rm -rf ' + '\"' + comp_filename + '\"', shell=True)

    is_silent = 0
    fixCRC(part_id[part_nr])


def compress_MODELEXT(part_nr, in2_file):
    global in_file

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)

        MODELEXT_SIZE = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_TYPE = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_NUMBER = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_VERSION = struct.unpack('<I', fin.read(4))[0]
        
        if not ((MODELEXT_TYPE == 1) and (MODELEXT_VERSION == 0x16072219) and (str(struct.unpack('8s', fin.read(8))[0])[2:-1] == 'MODELEXT')):
            return
        
        fin.seek(MODELEXT_SIZE - 24, 1)
        
        # OPTIMIZED: Use file writing directly instead of building in memory
        comp_filename = in2_file.replace('uncomp_partitionID', 'comp_partitionID')
        
        with open(comp_filename, 'wb') as fout:
            # Write first sub-partition data
            inputname = in2_file + '_' + str(MODELEXT_TYPE) + '_INFO'
            if not os.path.isfile(inputname):
                print('\033[91m%s sub-partition file does not found, exit\033[0m' % (inputname))
                exit(0)
            
            with open(inputname, 'rb') as fadd:
                print('Compressing \033[93m%s sub-partition file...\033[0m' % (inputname))
                fout.write(struct.pack('<I', MODELEXT_SIZE))
                fout.write(struct.pack('<I', MODELEXT_TYPE))
                fout.write(struct.pack('<I', MODELEXT_NUMBER))
                fout.write(struct.pack('<I', MODELEXT_VERSION))
                # Stream the file content
                while True:
                    chunk = fadd.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    fout.write(chunk)

            # Continue with next sub-parts
            while True:
                MODELEXT_SIZE = struct.unpack('<I', fin.read(4))[0]
                MODELEXT_TYPE = struct.unpack('<I', fin.read(4))[0]
                MODELEXT_NUMBER = struct.unpack('<I', fin.read(4))[0]
                MODELEXT_VERSION = struct.unpack('<I', fin.read(4))[0]
                
                type_str = ''
                if MODELEXT_TYPE == 1:
                    type_str = '_INFO'
                elif MODELEXT_TYPE == 2:
                    type_str = '_BIN_INFO'
                elif MODELEXT_TYPE == 3:
                    type_str = '_PINMUX_CFG'
                elif MODELEXT_TYPE == 4:
                    type_str = '_INTDIR_CFG'
                elif MODELEXT_TYPE == 5:
                    type_str = '_EMB_PARTITION'
                elif MODELEXT_TYPE == 6:
                    type_str = '_GPIO_INFO'
                elif MODELEXT_TYPE == 7:
                    type_str = '_DRAM_PARTITION'
                elif MODELEXT_TYPE == 8:
                    type_str = '_MODEL_CFG'
                
                if type_str == '':
                    break
                
                inputname = in2_file + '_' + str(MODELEXT_TYPE) + type_str
                if not os.path.isfile(inputname):
                    print('\033[91m%s sub-partition file does not found, exit\033[0m' % (inputname))
                    exit(0)

                print('Compressing \033[93m%s sub-partition file...\033[0m' % (inputname))
                fout.write(struct.pack('<I', MODELEXT_SIZE))
                fout.write(struct.pack('<I', MODELEXT_TYPE))
                fout.write(struct.pack('<I', MODELEXT_NUMBER))
                fout.write(struct.pack('<I', MODELEXT_VERSION))
                
                with open(inputname, 'rb') as fadd:
                    while True:
                        chunk = fadd.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        fout.write(chunk)
                
                fin.seek(MODELEXT_SIZE - 16, 1)
            
            # Add padding
            current_size = fout.tell()
            addsize = (current_size % 4)
            if addsize != 0:
                addsize = 4 - addsize
                fout.write(b'\x00' * addsize)

    # Fix total file size in MODELEXT INFO
    with open(comp_filename, 'r+b') as fout:
        fout.seek(0x30, 0)
        fout.write(struct.pack('<I', os.path.getsize(comp_filename)))

    if not os.path.isfile(comp_filename):
        print('\033[91m%s compressed partition file does not found, exit\033[0m' % comp_filename)
        exit(0)

    global is_silent
    is_silent = 1

    partition_replace(part_id[part_nr], 0, comp_filename)

    subprocess.run('rm -rf ' + '\"' + comp_filename + '\"', shell=True)

    is_silent = 0
    fixCRC(part_id[part_nr])


def compress(part_nr, in2_file):
    global in_file

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr], 0)
        FourCC = fin.read(4)

        if FourCC == b'CKSM':
            fin.seek(part_startoffset[part_nr] + 0x40, 0)
            FourCC = fin.read(4)

            if FourCC == b'UBI#':
                compress_CKSM_UBI(part_nr, in2_file)
                return

            if FourCC == b'BCL1':
                compress_CKSM_BCL(part_nr, in2_file)
                return

            if struct.unpack('>I', FourCC)[0] == 0x3AFF26ED:
                compress_CKSM_SPARSE(part_nr, in2_file)
                return
        else:
            if FourCC == b'BCL1':
                compress_BCL(part_nr, in2_file)
                return

            if struct.unpack('>I', FourCC)[0] == 0xD00DFEED:
                compress_FDT(part_nr, in2_file)
                return

            MODELEXT_TYPE = struct.unpack('<I', fin.read(4))[0]
            fin.read(4)
            MODELEXT_VERSION = struct.unpack('<I', fin.read(4))[0]
            if (MODELEXT_TYPE == 1) and (MODELEXT_VERSION == 0x16072219) and (str(struct.unpack('8s', fin.read(8))[0])[2:-1] == 'MODELEXT'):
                compress_MODELEXT(part_nr, in2_file)
                return

    print("\033[91mThis partition type is not supported for compression\033[0m")
    exit(0)


# OPTIMIZED: BCL1 compression with reduced memory usage
def BCL1_compress(part_nr, in_offset, in2_file):
    global in_file
    global FW_BOOTLOADER

    with open(in_file, 'rb') as fin:
        fin.seek(part_startoffset[part_nr] + in_offset, 0)
        FourCC = fin.read(4)
        if FourCC != b'BCL1':
            print("\033[91mBCL1 marker not found, exit\033[0m")
            sys.exit(1)

        fin.read(2)  # skip old CRC
        Algorithm = struct.unpack('>H', fin.read(2))[0]

        if (Algorithm != 0x09) & (Algorithm != 0x0B) & (Algorithm != 0x0C):
            print("\033[91mCompression algo %0X is not supported\033[0m" % Algorithm)
            sys.exit(1)

        unpacked_part_size = struct.unpack('>I', fin.read(4))[0]

        if (Algorithm == 0x0B):
            fin.seek(part_startoffset[part_nr] + in_offset + 0x10, 0)
            LZMA_Properties = struct.unpack('B', fin.read(1))[0]
            LZMA_DictionarySize = struct.unpack('<I', fin.read(4))[0]
            LZMA_UncompressedSize64_Low = struct.unpack('<I', fin.read(4))[0]
            LZMA_UncompressedSize64_High = struct.unpack('<I', fin.read(4))[0]
        
    out = in2_file.replace('uncomp_partitionID', 'comp_partitionID')

    # OPTIMIZED: Read input file in chunks for CRC calculation
    with open(in2_file, 'rb') as fin:
        # First pass: calculate file size and check for CRC locations
        fin.seek(0, 2)
        file_size = fin.tell()
        fin.seek(0, 0)
        
        # Read only necessary portions for CRC check
        header_chunk = fin.read(min(0x500, file_size))
    
    dataread = bytearray(header_chunk)
    
    # Check CRC locations
    needs_crc_fix = False
    crc_offset = 0
    
    if len(dataread) > 0x46D:
        if (dataread[0x6C] == 0xFF) & (dataread[0x6D] == 0xFF) & (dataread[0x46C] == 0x55) & (dataread[0x46D] == 0xAA):
            needs_crc_fix = True
            crc_offset = 0x46E
        elif (dataread[0x6C] == 0x55) & (dataread[0x6D] == 0xAA):
            needs_crc_fix = True
            crc_offset = 0x6E
        elif len(dataread) > 0x16D and (dataread[0x16C] == 0x55) & (dataread[0x16D] == 0xAA):
            needs_crc_fix = True
            crc_offset = 0x16E
    
    # Read full file only if CRC fix is needed
    if needs_crc_fix:
        with open(in2_file, 'rb') as fin:
            dataread = bytearray(fin.read())
        
        newCRC = MemCheck_CalcCheckSum16Bit(in2_file, 0, len(dataread), crc_offset)
        oldCRC = (dataread[crc_offset + 1]<<8)|dataread[crc_offset]
        
        if is_silent != 1:
            if oldCRC != newCRC:
                print('Uncompressed data partitionID %i at \033[94m0x%04X\033[0m: ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (part_id[part_nr], crc_offset, oldCRC, newCRC))
            else:
                print('Uncompressed data partitionID %i at \033[94m0x%04X\033[0m: ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (part_id[part_nr], crc_offset, oldCRC, newCRC))
        
        dataread[crc_offset] = (newCRC & 0xFF)
        dataread[crc_offset + 1] = ((newCRC >> 8) & 0xFF)
    else:
        # Read full file for compression
        with open(in2_file, 'rb') as fin:
            dataread = bytearray(fin.read())

    # LZ77 compress
    if Algorithm == 0x09:
        insize = len(dataread)

        # OPTIMIZED: Use dictionary instead of large array for jump table
        work_dict = {}  # symbol -> last position
        work_chain = {}  # position -> previous position with same symbol
        
        # Build jump table using dictionary
        for i in range(insize-1):
            symbols = ((dataread[i]) << 8) | (dataread[i+1])
            if symbols in work_dict:
                work_chain[i] = work_dict[symbols]
            else:
                work_chain[i] = -1
            work_dict[symbols] = i
        
        work_chain[insize-1] = -1

        # Find least common byte for marker
        histogram = [0] * 256
        for b in dataread:
            histogram[b] += 1
        marker = histogram.index(min(histogram))

        # OPTIMIZED: Write compressed data directly to file
        with open(out, 'wb') as fout:
            # Write BCL1 header placeholder
            fout.write(struct.pack('>I', 0x42434C31))  # BCL1
            fout.write(struct.pack('<H', 0x0000))  # CRC placeholder
            fout.write(struct.pack('>H', Algorithm))
            
            if unpacked_part_size > len(dataread):
                fout.write(struct.pack('>I', unpacked_part_size))
            else:
                fout.write(struct.pack('>I', len(dataread)))
            
            # Packed size placeholder
            packed_size_pos = fout.tell()
            fout.write(struct.pack('>I', 0))
            
            # Write marker
            fout.write(struct.pack('B', marker))
            
            startT = datetime.now()
            oldcurrprogress = 0

            LZ_MAX_OFFSET = 100000
            inpos = 0
            outpos = 1
            bytesleft = insize

            while bytesleft > 3:
                bestlength = 3
                bestoffset = 0

                symbols = ((dataread[inpos]) << 8) | (dataread[inpos+1]) if inpos + 1 < insize else 0
                j = work_dict.get(symbols, -1)
                
                if j != -1:
                    j = work_chain.get(inpos, -1)

                while (j != -1) and ((inpos - j) < LZ_MAX_OFFSET):
                    if (j + bestlength >= insize) or (inpos + bestlength >= insize):
                        break

                    if dataread[j + bestlength] == dataread[inpos + bestlength]:
                        offset = inpos - j
                        maxlength = bytesleft if bytesleft < offset else offset

                        length = 2
                        while (length < maxlength) and (dataread[inpos + length] == dataread[j + length]):
                            length += 1

                        if length > bestlength:
                            bestlength = length
                            bestoffset = offset

                    j = work_chain.get(j, -1)

                if( (bestlength > 7) |
                    ((bestlength == 4) & (bestoffset <= 0x0000007f)) |
                    ((bestlength == 5) & (bestoffset <= 0x00003fff)) |
                    ((bestlength == 6) & (bestoffset <= 0x001fffff)) |
                    ((bestlength == 7) & (bestoffset <= 0x0fffffff)) ):
                        fout.write(struct.pack('B', marker))
                        outpos += 1

                        # Write length
                        buf = 0
                        y = bestlength >> 3
                        num_bytes = 5
                        while num_bytes >= 2:
                            if y & 0xfe000000 != 0:
                                break
                            y <<= 7
                            num_bytes -= 1
                        
                        i = num_bytes-1
                        while i >= 0:
                            b = (bestlength >> (i*7)) & 0x0000007f
                            if i > 0:
                                b |= 0x00000080
                            buf = (buf<<8) | b
                            i -= 1
                        
                        outpos += num_bytes
                        while num_bytes > 0:
                            fout.write(struct.pack('B', (buf>>(8*(num_bytes - 1)))&0xFF))
                            num_bytes -= 1

                        # Write offset
                        buf = 0
                        y = bestoffset >> 3
                        num_bytes = 5
                        while num_bytes >= 2:
                            if y & 0xfe000000 != 0:
                                break
                            y <<= 7
                            num_bytes -= 1
                        
                        i = num_bytes-1
                        while i >= 0:
                            b = (bestoffset >> (i*7)) & 0x0000007f
                            if i > 0:
                                b |= 0x00000080
                            buf = (buf<<8) | b
                            i -= 1
                        
                        outpos += num_bytes
                        while num_bytes > 0:
                            fout.write(struct.pack('B', (buf>>(8*(num_bytes - 1)))&0xFF))
                            num_bytes -= 1

                        inpos += bestlength
                        bytesleft -= bestlength
                else:
                    symbol = dataread[inpos]
                    inpos += 1
                    fout.write(struct.pack('B', symbol))
                    outpos += 1
                    if symbol == marker:
                        fout.write(struct.pack('B', 0))
                        outpos += 1
                    bytesleft -= 1

                currprogress = round(inpos/insize*100)
                if currprogress > oldcurrprogress:
                    updateProgressBar(currprogress)
                    oldcurrprogress = currprogress

            # Dump remaining bytes
            while inpos < insize:
                if dataread[inpos] == marker:
                    fout.write(struct.pack('B', marker))
                    outpos += 1
                    fout.write(struct.pack('B', 0))
                    outpos += 1
                else:
                    fout.write(struct.pack('B', dataread[inpos]))
                    outpos += 1
                inpos += 1

            endT = datetime.now()
            print("elapsed: %s" % str(endT - startT))

            # Add padding
            addsize = 0
            if (FW_HDR2 == 1) | ((FW_HDR == 1) & (part_id[part_nr] == 0)) | (FW_HDR == 0 and FW_BOOTLOADER == 0):
                addsize = (outpos % 4)
                if addsize != 0:
                    addsize = 4 - addsize
                    fout.write(b'\x00' * addsize)

            # Update packed size in header
            fout.seek(packed_size_pos, 0)
            fout.write(struct.pack('>I', outpos + addsize))

    # LZMA compress
    elif Algorithm == 0x0B:
        lc = LZMA_Properties % 9
        LZMA_Properties = LZMA_Properties // 9
        pb = LZMA_Properties // 5
        lp = LZMA_Properties % 5

        if LZMA_DictionarySize < (1 << 12):
            LZMA_DictionarySize = (1 << 12)
    
        fast_bytes = 40
        search_depth = 16 + fast_bytes//2

        my_filters = [{"id":lzma.FILTER_LZMA1, "mode":lzma.MODE_NORMAL, "dict_size":LZMA_DictionarySize, "mf":lzma.MF_BT4, "nice_len":fast_bytes, "depth":search_depth, "lc":lc, "lp":lp, "pb":pb}]

        compressed_data = lzma.compress(dataread, format = lzma.FORMAT_ALONE, filters = my_filters)

        # Write to file
        with open(out, 'wb') as fout:
            fout.write(struct.pack('>I', 0x42434C31))
            fout.write(struct.pack('<H', 0x0000))
            fout.write(struct.pack('>H', Algorithm))
            
            if unpacked_part_size > len(dataread):
                fout.write(struct.pack('>I', unpacked_part_size))
            else:
                fout.write(struct.pack('>I', len(dataread)))

            addsize = 0
            if (FW_HDR2 == 1) | ((FW_HDR == 1) & (part_id[part_nr] == 0)) | (FW_HDR == 0 and FW_BOOTLOADER == 0):
                addsize = (len(compressed_data) % 4)
                if addsize != 0:
                    addsize = 4 - addsize

            fout.write(struct.pack('>I', len(compressed_data) + addsize))
            fout.write(compressed_data)
            
            if addsize > 0:
                fout.write(b'\x00' * addsize)

    # ZLIB compress
    elif Algorithm == 0x0C:
        compressed_data = zlib.compress(dataread)

        with open(out, 'wb') as fout:
            fout.write(struct.pack('>I', 0x42434C31))
            fout.write(struct.pack('<H', 0x0000))
            fout.write(struct.pack('>H', Algorithm))
            
            if unpacked_part_size > len(dataread):
                fout.write(struct.pack('>I', unpacked_part_size))
            else:
                fout.write(struct.pack('>I', len(dataread)))

            addsize = 0
            if (FW_HDR2 == 1) | ((FW_HDR == 1) & (part_id[part_nr] == 0)) | (FW_HDR == 0 and FW_BOOTLOADER == 0):
                addsize = (len(compressed_data) % 4)
                if addsize != 0:
                    addsize = 4 - addsize

            fout.write(struct.pack('>I', len(compressed_data) + addsize))
            fout.write(compressed_data)
            
            if addsize > 0:
                fout.write(b'\x00' * addsize)

    # Calculate and update CRC
    if FW_BOOTLOADER == 0:
        newCRC = MemCheck_CalcCheckSum16Bit(out, 0, os.path.getsize(out) - 16 + 16, 0x4)
        with open(out, 'r+b') as fout:
            fout.seek(4, 0)
            fout.write(struct.pack('<H', newCRC))


def updateProgressBar(value):
    line = '\r\033[93m%s%%\033[0m[\033[94m%s\033[0m%s]' % ( str(value).rjust(3), '#' * round((float(value)/100) * 70), '-' * round(70 -((float(value)/100) * 70)))
    print(line, end='')
    sys.stdout.flush()
    if value == 100:
        print('')


def uncompressDTB(in_file, out_filename = ''):
    with open(in_file, 'rb') as fin:
        FourCC = fin.read(4)

    if struct.unpack('>I', FourCC)[0] == 0xD00DFEED:
        if out_filename == '':
            out_filename = os.path.splitext(in_file)[0] + '.dts'
        os.system('dtc -qqq -I dtb -O dts ' + '\"' + in_file + '\"' + ' -o ' + '\"' + out_filename + '\"')
    else:
        print("\033[91mDTB marker not found, exit\033[0m")
        sys.exit(1)


def compressToDTB(in_file, out_filename = ''):
    if out_filename == '':
        out_filename = os.path.splitext(in_file)[0] + '.dtb'
    os.system('dtc -qqq -I dts -O dtb ' + '\"' + in_file + '\"' + ' -o ' + '\"' + out_filename + '\"')


def uncompress(in_offset, out_filename, size):
    global in_file

    with open(in_file, 'rb') as fin:
        fin.seek(in_offset, 0)
        FourCC = fin.read(4)

        # FDT (DTB)
        if struct.unpack('>I', FourCC)[0] == 0xD00DFEED:
            # OPTIMIZED: Stream extraction
            fin.seek(in_offset, 0)
            with open(out_filename + '_tempfile', 'wb') as fpartout:
                bytes_remaining = size
                while bytes_remaining > 0:
                    chunk_size = min(CHUNK_SIZE, bytes_remaining)
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fpartout.write(chunk)
                    bytes_remaining -= len(chunk)
            
            os.system('dtc -qqq -I dtb -O dts ' + '\"' + out_filename + '_tempfile' + '\"' + ' -o ' + '\"' + out_filename + '\"')
            os.system('rm -rf ' + '\"' + out_filename + '_tempfile' + '\"')
            return

        if FourCC == b'BCL1':
            BCL1_uncompress(in_offset, out_filename)
            return

        if FourCC == b'UBI#':
            os.system('sudo rm -rf ' + '\"' + out_filename + '\"')
            os.system('mkdir ' + '\"' + out_filename + '\"')

            # OPTIMIZED: Stream extraction
            fin.seek(in_offset, 0)
            with open(out_filename + '/tempfile', 'wb') as fpartout:
                bytes_remaining = size
                while bytes_remaining > 0:
                    chunk_size = min(CHUNK_SIZE, bytes_remaining)
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fpartout.write(chunk)
                    bytes_remaining -= len(chunk)

            os.system('sudo ubireader_extract_files -k -i -f ' + '-o ' + '\"' + out_filename + '\"' + ' ' + '\"' + out_filename + '/tempfile' + '\"')
            os.system('rm -rf ' + '\"' + out_filename + '/tempfile' + '\"')
            return

        # SPARSE EXT4
        if struct.unpack('>I', FourCC)[0] == 0x3AFF26ED:
            os.system('rm -rf ' + '\"' + out_filename + '\"')
            os.system('mkdir ' + '\"' + out_filename + '\"')
            os.system('mkdir ' + '\"' + out_filename + '/mount' + '\"')

            # OPTIMIZED: Stream extraction
            fin.seek(in_offset, 0)
            with open(out_filename + '/tempfile', 'wb') as fpartout:
                bytes_remaining = size
                while bytes_remaining > 0:
                    chunk_size = min(CHUNK_SIZE, bytes_remaining)
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fpartout.write(chunk)
                    bytes_remaining -= len(chunk)

            subprocess.run('simg2img ' + '\"' + out_filename + '/tempfile' + '\"' + ' ' + '\"' + out_filename + '/tempfile.ext4' + '\"', shell=True)
            os.system('mount ' + '\"' + out_filename + '/tempfile.ext4' + '\"' + ' ' + '\"' + out_filename + '/mount' + '\"')
            os.system('rm -rf ' + '\"' + out_filename + '/tempfile' + '\"')
            return
        
        # MODELEXT
        MODELEXT_SIZE = struct.unpack('<I', FourCC)[0]
        MODELEXT_TYPE = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_NUMBER = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_VERSION = struct.unpack('<I', fin.read(4))[0]
        
        if (MODELEXT_TYPE == 1) and (MODELEXT_VERSION == 0x16072219) and (str(struct.unpack('8s', fin.read(8))[0])[2:-1] == 'MODELEXT'):
            fin.seek(-8, 1)
            data = fin.read(MODELEXT_SIZE - 16)
            type_str = ''

            while(1):
                if MODELEXT_TYPE == 1:
                    type_str = '_INFO'
                elif MODELEXT_TYPE == 2:
                    type_str = '_BIN_INFO'
                elif MODELEXT_TYPE == 3:
                    type_str = '_PINMUX_CFG'
                elif MODELEXT_TYPE == 4:
                    type_str = '_INTDIR_CFG'
                elif MODELEXT_TYPE == 5:
                    type_str = '_EMB_PARTITION'
                elif MODELEXT_TYPE == 6:
                    type_str = '_GPIO_INFO'
                elif MODELEXT_TYPE == 7:
                    type_str = '_DRAM_PARTITION'
                elif MODELEXT_TYPE == 8:
                    type_str = '_MODEL_CFG'
                
                if type_str == '':
                    return

                print('Save \033[93m%s\033[0m sub-partition' %(type_str[1:]))
                with open(out_filename + '_' + str(MODELEXT_TYPE) + type_str, 'wb') as fpartout:
                    fpartout.write(data)

                MODELEXT_SIZE = struct.unpack('<I', fin.read(4))[0]
                MODELEXT_TYPE = struct.unpack('<I', fin.read(4))[0]
                MODELEXT_NUMBER = struct.unpack('<I', fin.read(4))[0]
                MODELEXT_VERSION = struct.unpack('<I', fin.read(4))[0]
                type_str = ''
                data = fin.read(MODELEXT_SIZE - 16)
            return

    print("\033[91mOnly FDT(DTB), BCL1, UBI, SPARSE and MODELEXT partitions is supported now, exit\033[0m")


# OPTIMIZED: BCL1 uncompress with streaming output
def BCL1_uncompress(in_offset, out_filename):
    global in_file

    with open(in_file, 'rb') as fin:
        fin.seek(in_offset, 0)
        FourCC = fin.read(4)
        if FourCC != b'BCL1':
            print("\033[91mBCL1 marker not found, exit\033[0m")
            sys.exit(1)

        fin.read(2)
        Algorithm = struct.unpack('>H', fin.read(2))[0]
        if (Algorithm != 0x09) & (Algorithm != 0x0B) & (Algorithm != 0x0C):
            print("\033[91mCompression algo %0X is not supported\033[0m" % Algorithm)
            sys.exit(1)

        outsize = struct.unpack('>I', fin.read(4))[0]
        insize = struct.unpack('>I', fin.read(4))[0]

        in_offset = in_offset + 0x10
        fin.seek(in_offset, 0)

        # LZ77 uncompress
        if Algorithm == 0x09:
            marker = struct.unpack('B', fin.read(1))[0]
            inpos = 1
            
            # OPTIMIZED: Use file writing with buffer
            with open(out_filename, 'wb') as fout:
                outputbuf = bytearray()
                BUFFER_LIMIT = CHUNK_SIZE
                
                outpos = 0
                while((inpos < insize) & (outpos < outsize)):
                    symbol = struct.unpack('B', fin.read(1))[0]
                    inpos += 1
            
                    if symbol == marker:
                        readbyte = struct.unpack('B', fin.read(1))[0]
                        if readbyte == 0:
                            outputbuf.append(marker)
                            outpos += 1
                            inpos += 1
                        else:
                            # Read length
                            y = 0
                            num_bytes = 0
                            b = readbyte
                            y = (y << 7) | (b & 0x0000007f)
                            num_bytes += 1
                            
                            while (b & 0x00000080) != 0:
                                b = struct.unpack('B', fin.read(1))[0]
                                y = (y << 7) | (b & 0x0000007f)
                                num_bytes += 1
            
                            length = y
                            inpos += num_bytes
                            
                            # Read offset
                            y = 0
                            num_bytes = 0
                            b = struct.unpack('B', fin.read(1))[0]
                            y = (y << 7) | (b & 0x0000007f)
                            num_bytes += 1
                            
                            while (b & 0x00000080) != 0:
                                b = struct.unpack('B', fin.read(1))[0]
                                y = (y << 7) | (b & 0x0000007f)
                                num_bytes += 1
            
                            offset = y
                            inpos += num_bytes
            
                            # Copy from history
                            for i in range(length):
                                outputbuf.append(outputbuf[outpos - offset])
                                outpos += 1
                    else:
                        outputbuf.append(symbol)
                        outpos += 1

                    # Flush buffer if it gets too large
                    if len(outputbuf) >= BUFFER_LIMIT:
                        fout.write(outputbuf)
                        # Keep only recent history needed for LZ77 lookback
                        if len(outputbuf) > BUFFER_LIMIT + 100000:
                            written = len(outputbuf) - 100000
                            outputbuf = outputbuf[written:]
                            outpos = len(outputbuf)

                # Write remaining buffer
                fout.write(outputbuf)

        # LZMA uncompress
        elif Algorithm == 0x0B:
            dataread = fin.read(insize)
            decompress = decompress_lzma(dataread)[:outsize]
            
            with open(out_filename, 'wb') as fout:
                fout.write(decompress)

        # ZLIB uncompress
        elif Algorithm == 0x0C:
            dataread = fin.read(insize)
            decompress = zlib.decompress(dataread)
            
            with open(out_filename, 'wb') as fout:
                fout.write(decompress)

    # Print partition info
    with open(out_filename, 'rb') as fin:
        # Read only necessary portions
        header = fin.read(min(0x500, os.path.getsize(out_filename)))
    
    if len(header) > 0x46D:
        if (header[0x6C] == 0xFF) & (header[0x6D] == 0xFF) & (header[0x46C] == 0x55) & (header[0x46D] == 0xAA):
            print('Partition data: Name="\033[93m%s\033[0m", Date="\033[93m%s\033[0m", Size=%s, CRC Offset=\033[93m0x%04X\033[0m, CRC=\033[93m0x%04X\033[0m' % (str(struct.unpack('8s',header[0x450:0x458])[0])[2:-1].replace('\\x00',''), str(struct.unpack('8s',header[0x460:0x468])[0])[2:-1], '\033[93m{:,}\033[0m'.format(struct.unpack('<I', header[0x468:0x46C])[0]), 0x46E, struct.unpack('<H', header[0x46E:0x470])[0]))
        elif (header[0x6C] == 0x55) & (header[0x6D] == 0xAA):
            print('Partition data: Name="\033[93m%s\033[0m", Date="\033[93m%s\033[0m", Size=%s, CRC Offset=\033[93m0x%04X\033[0m, CRC=\033[93m0x%04X\033[0m' % (str(struct.unpack('8s',header[0x50:0x58])[0])[2:-1].replace('\\x00',''), str(struct.unpack('8s',header[0x60:0x68])[0])[2:-1], '\033[93m{:,}\033[0m'.format(struct.unpack('<I', header[0x68:0x6C])[0]), 0x6E, struct.unpack('<H', header[0x6E:0x70])[0]))
        elif len(header) > 0x16D and (header[0x16C] == 0x55) & (header[0x16D] == 0xAA):
            print('Partition with 0x100 data at begin: Name="\033[93m%s\033[0m", Date="\033[93m%s\033[0m", Size=%s, CRC Offset=\033[93m0x%04X\033[0m, CRC=\033[93m0x%04X\033[0m' % (str(struct.unpack('8s',header[0x150:0x158])[0])[2:-1].replace('\\x00',''), str(struct.unpack('8s',header[0x160:0x168])[0])[2:-1], '\033[93m{:,}\033[0m'.format(struct.unpack('<I', header[0x168:0x16C])[0]), 0x16E, struct.unpack('<H', header[0x16E:0x170])[0]))
        else:
            print('Partition data without CRC')


def decompress_lzma(data):
    results = []
    while True:
        decomp = lzma.LZMADecompressor(lzma.FORMAT_ALONE, None, None)
        try:
            res = decomp.decompress(data)
        except lzma.LZMAError:
            if results:
                break
            else:
                raise
        results.append(res)
        data = decomp.unused_data
        if not data:
            break
        if not decomp.eof:
            raise lzma.LZMAError("Compressed data ended before the end-of-stream marker was reached")
    return b"".join(results)


def fillIDPartNames(startat):
    global in_file
    
    with open(in_file, 'rb') as fin:
        fin.seek(startat+0x34, 0)

        starting = struct.unpack('>I', fin.read(4))[0]
        while(starting == 0x00000001):
            id_length = 0
            t = struct.unpack('B', fin.read(1))[0]
            while(t != 0x00):
                id_length+=1
                t = struct.unpack('B', fin.read(1))[0]
            
            fin.seek(-1*(id_length+1), 1)
            idname = str(struct.unpack('%ds' % (id_length), fin.read(id_length))[0])[2:-1]
            dtbpart_ID.append(idname)
            fin.read(4 - (id_length%4))
            
            fin.read(4)
            lengthname = struct.unpack('>I', fin.read(4))[0]
            fin.read(4)
            shortname = str(struct.unpack('%ds' % (lengthname-1), fin.read(lengthname-1))[0])[2:-1]
            dtbpart_name.append(shortname)
            if lengthname > 1:
                fin.read(4 - ((lengthname-1)%4))
            else:
                fin.read(4)
            
            fin.read(4)
            lengthfilename = struct.unpack('>I', fin.read(4))[0]
            fin.read(4)
            filename = str(struct.unpack('%ds' % (lengthfilename-1), fin.read(lengthfilename-1))[0])[2:-1]
            dtbpart_filename.append(filename)
            if lengthfilename > 1:
                fin.read(4 - ((lengthfilename-1)%4))
            else:
                fin.read(4)
            
            fin.read(4)
            starting = struct.unpack('>I', fin.read(4))[0]


def GetPartitionInfo(start_offset, part_size, partID, addinfo = 1):
    global in_file
    global is_ARM64
    global FW_BOOTLOADER

    with open(in_file, 'rb') as fin:
        fin.seek(start_offset, 0)
        partfirst4bytes = struct.unpack('>I', fin.read(4))[0]

        # dtb
        if partfirst4bytes == 0xD00DFEED:
            temp_parttype = 'device tree blob (dtb)'
            CRC = 0
            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(0)
                part_crcCalc.append(CRC)

                fin.seek(start_offset, 0)
                # OPTIMIZED: Only read necessary portion for DTB parsing
                dtb_header = fin.read(min(part_size, 4096))  # DTB header is usually small
                startat = dtb_header.find(b'NVTPACK_FW_INI_16072017')
                if startat != -1:
                    fillIDPartNames(start_offset + startat)

            return temp_parttype, CRC

        # atf = ARM Trusted Firmware-A
        if len(dtbpart_name) != 0 and dtbpart_name[partID] == 'atf':
            temp_parttype = 'ARM Trusted Firmware'
            CRC = 0
            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(0)
                part_crcCalc.append(CRC)
            return temp_parttype, CRC

        # uboot
        if len(dtbpart_name) != 0 and dtbpart_name[partID] == 'uboot':
            temp_parttype = 'uboot'
            CRC = MemCheck_CalcCheckSum16Bit(in_file, start_offset, part_size, 0x36E)
            if addinfo:
                part_type.append(temp_parttype)
                fin.seek(start_offset + 0x36E, 0)
                part_crc.append(struct.unpack('<H', fin.read(2))[0])
                part_crcCalc.append(CRC)
            return temp_parttype, CRC

        # uImage header
        if partfirst4bytes == 0x27051956:
            temp_parttype = 'uImage'
            MultiFileImage_content = ''

            fin.seek(start_offset + 28, 0)
            temp = struct.unpack('B', fin.read(1))[0]
            if temp in uImage_os:
                temp_parttype += ', OS: ' + '\"\033[93m' + uImage_os[temp] + '\033[0m\"'

            found_ARM64 = 0
            temp = struct.unpack('B', fin.read(1))[0]
            if temp in uImage_arch:
                temp_parttype += ', CPU: ' + '\"\033[93m' + uImage_arch[temp] + '\033[0m\"'
                if (temp == 22):
                    found_ARM64 = 1

            temp = struct.unpack('B', fin.read(1))[0]
            if temp in uImage_imagetype:
                temp_parttype += ', Image type: ' + '\"\033[93m' + uImage_imagetype[temp] + '\033[0m\"'

                if(temp == 2 and found_ARM64 == 1):
                    is_ARM64 = 1
                
                if temp == 4:
                    currpos = fin.tell()
                    fin.seek(start_offset + 64, 0)
                    temp = struct.unpack('>I', fin.read(4))[0]
                    MultiFileImage_amount = 0
                    MultiFileImage_content = os.linesep + 'Contents:' + os.linesep
                    while(temp != 0):
                        MultiFileImage_amount += 1
                        MultiFileImage_content += 'Image ' + str(MultiFileImage_amount) + ': ' + '{:,}'.format(temp) + ' bytes' + os.linesep
                        temp = struct.unpack('>I', fin.read(4))[0]

                    fin.seek(currpos, 0)

            temp = struct.unpack('B', fin.read(1))[0]
            if temp in uImage_compressiontype:
                temp_parttype += ', Compression type: ' + '\"\033[93m' + uImage_compressiontype[temp] + '\033[0m\"'

            temp_parttype += ', Image name: ' + '\"\033[93m' + str(fin.read(32)).replace("\\x00","")[2:-1] + '\033[0m\"'

            fin.seek(start_offset + 8, 0)
            temp = struct.unpack('>I', fin.read(4))[0]
            temp_parttype += ', created: ' + '\"\033[93m' + datetime.fromtimestamp(temp, timezone.utc).strftime('%Y-%m-%d %H:%M:%S') + '\033[0m\"'

            temp = struct.unpack('>I', fin.read(4))[0]
            temp_parttype += ', size: ' + '\"\033[93m{:,}\033[0m" bytes'.format(temp)

            if MultiFileImage_content != '':
                temp_parttype += MultiFileImage_content

            CRC = 0
            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(0)
                part_crcCalc.append(CRC)
            return temp_parttype, CRC

        # Compressed ext4 file system SPARSE image format
        if partfirst4bytes == 0x3AFF26ED:
            temp_parttype = '\033[93mSPARSE EXT4 image\033[0m'
            CRC = 0

            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(0)
                part_crcCalc.append(CRC)
            return temp_parttype, CRC

        # BCL1
        if partfirst4bytes == 0x42434C31:
            temp_parttype = '\033[93mBCL1\033[0m'

            uiChkValue = struct.unpack('<H', fin.read(2))[0]

            compressAlgo = struct.unpack('>H', fin.read(2))[0]
            if compressAlgo in compressAlgoTypes:
                temp_parttype += '[\033[93m' + compressAlgoTypes[compressAlgo] + '\033[0m]'
            else:
                temp_parttype += '[\033[91mcompr.algo:0x%0X\033[0m' % compressAlgo + ']'

            BCL1unpackedSize = struct.unpack('>I', fin.read(4))[0]
            BCL1packedSize = struct.unpack('>I', fin.read(4))[0]
            temp_parttype += ' \033[93m{:,}\033[0m'.format(BCL1unpackedSize) + ' packed to ' + '\033[93m{:,}\033[0m bytes'.format(BCL1packedSize)

            CRC = MemCheck_CalcCheckSum16Bit(in_file, start_offset, BCL1packedSize + 0x10, 0x4)

            if FW_BOOTLOADER == 1:
                CRC = 0

            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(uiChkValue)
                part_crcCalc.append(CRC)
            return temp_parttype, CRC

        # UBI#
        if partfirst4bytes ==  0x55424923:
            temp_parttype = '\033[93mUBI\033[0m'

            fin.seek(0x100C, 1)
            id_length = 0
            t = struct.unpack('B', fin.read(1))[0]
            while(t != 0x00):
                id_length += 1
                t = struct.unpack('B', fin.read(1))[0]
            
            fin.seek(-1*(id_length+1), 1)
            UBIname = str(struct.unpack('%ds' % (id_length), fin.read(id_length))[0])[2:-1]
            temp_parttype += ' \"\033[93m' + UBIname + '\033[0m\"'
            CRC = 0

            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(0)
                part_crcCalc.append(CRC)
            return temp_parttype, CRC

        # CKSM
        if partfirst4bytes == 0x434B534D:
            if struct.unpack('>I', fin.read(4))[0] == 0x19070416:
                uiChkMethod = struct.unpack('<I', fin.read(4))[0]
                uiChkValue = struct.unpack('<I', fin.read(4))[0]
                uiDataOffset = struct.unpack('<I', fin.read(4))[0]
                uiDataSize = struct.unpack('<I', fin.read(4))[0]
                uiPaddingSize = struct.unpack('<I', fin.read(4))[0]
                uiEmbType = struct.unpack('<I', fin.read(4))[0]

                temp_parttype = '\033[93mCKSM\033[0m'

                deeppart, calcCRC = GetPartitionInfo(start_offset + 0x40, 0, 0, 0)
                if deeppart != '':
                    temp_parttype += '\033[94m<--\033[0m' + deeppart

                CRC = MemCheck_CalcCheckSum16Bit(in_file, start_offset, uiDataOffset + uiDataSize + uiPaddingSize, 0xC)

                if addinfo:
                    part_type.append(temp_parttype)
                    part_crc.append(uiChkValue)
                    part_crcCalc.append(CRC)
                return temp_parttype, CRC

        # MODELEXT
        MODELEXT_SIZE = partfirst4bytes
        MODELEXT_TYPE = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_NUMBER = struct.unpack('<I', fin.read(4))[0]
        MODELEXT_VERSION = struct.unpack('<I', fin.read(4))[0]

        if (MODELEXT_TYPE == 1) and (MODELEXT_VERSION == 0x16072219) and (str(struct.unpack('8s', fin.read(8))[0])[2:-1] == 'MODELEXT'):
            temp_parttype = '\033[93mMODELEXT\033[0m'

            temp_parttype += ' INFO: Chip:\033[93m' + str(struct.unpack('8s', fin.read(8))[0]).replace("\\x00","")[2:-1] + '\033[0m'
            fin.read(8)
            temp_parttype += ', Build:\033[93m' + str(struct.unpack('8s', fin.read(8))[0]).replace("\\x00","")[2:-1] + '\033[0m'
            ext_bin_length = struct.unpack('<I', fin.read(4))[0]
            fin.seek(2, 1)
            uiChkValue = struct.unpack('<H', fin.read(2))[0]

            CRC = MemCheck_CalcCheckSum16Bit(in_file, start_offset, ext_bin_length, 0x36)

            if addinfo:
                part_type.append(temp_parttype)
                part_crc.append(uiChkValue)
                part_crcCalc.append(CRC)

            return temp_parttype, CRC
        else:
            fin.seek(start_offset + 4, 0)

    # unknown part
    if addinfo:
        part_type.append('\033[91munknown part\033[0m')
        part_crc.append(0)
        part_crcCalc.append(0)
    return '', 0


# OPTIMIZED: Stream-based partition extraction
def partition_extract(is_extract, is_extract_offset):
    global partitions_count
    global workdir

    part_nr = -1
    for a in range(partitions_count):
        if part_id[a] == is_extract:
            part_nr = a
            break
    
    if part_nr != -1:
        if workdir != '':
            out_file = workdir + '/' + in_file + '-partitionID' + str(part_id[part_nr])
        else:
            out_file = in_file + '-partitionID' + str(part_id[part_nr])

        if is_extract_offset != -1:
            if is_silent != 1:
                print('Extract partition ID %i from 0x%08X + 0x%08X to file \033[93m%s\033[0m' % (part_id[part_nr], part_startoffset[part_nr], is_extract_offset, out_file))
        else:
            if is_silent != 1:
                print('Extract partition ID %i from 0x%08X to file \033[93m%s\033[0m' % (part_id[part_nr], part_startoffset[part_nr], out_file))
            is_extract_offset = 0

        # OPTIMIZED: Stream extraction instead of reading entire partition
        with open(in_file, 'rb') as fin:
            fin.seek(part_startoffset[part_nr] + is_extract_offset, 0)
            with open(out_file, 'wb') as fpartout:
                bytes_remaining = part_size[part_nr] - is_extract_offset
                while bytes_remaining > 0:
                    chunk_size = min(CHUNK_SIZE, bytes_remaining)
                    chunk = fin.read(chunk_size)
                    if not chunk:
                        break
                    fpartout.write(chunk)
                    bytes_remaining -= len(chunk)
    else:
        print('\033[91mCould not find partiton with ID %i\033[0m' % is_extract)


def partition_replace(is_replace, is_replace_offset, is_replace_file):
    global partitions_count
    global NVTPACK_FW_HDR2_size
    global total_file_size
    
    part_nr = -1
    for a in range(partitions_count):
        if part_id[a] == is_replace:
            part_nr = a
            break
    
    if part_nr != -1:
        if not os.path.isfile(is_replace_file):
            print('\033[91m%s file does not found, exit\033[0m' % is_replace_file)
            exit(0)
    
        if is_silent != 1:
            print('Replace partition ID %i from 0x%08X + 0x%08X using inputfile \033[93m%s\033[0m' % (is_replace, part_startoffset[part_nr], is_replace_offset, is_replace_file))
        
        replace_size = os.path.getsize(is_replace_file)
        
        if (replace_size + is_replace_offset) == part_size[part_nr]:
            # Simple replacement without size change - can stream
            with open(is_replace_file, 'rb') as freplace:
                with open(in_file, 'r+b') as fin:
                    fin.seek(part_startoffset[part_nr] + is_replace_offset, 0)
                    while True:
                        chunk = freplace.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        fin.write(chunk)
        else:
            # Size changed - need more complex handling
            # Read replacement data
            with open(is_replace_file, 'rb') as freplace:
                replacedata = freplace.read()
            
            # Continue with complex replacement logic (similar to original)
            if FW_HDR2 == 1:
                with open(in_file, 'rb') as fin:
                    if part_nr + 1 < partitions_count:
                        fin.seek(part_startoffset[part_nr + 1], 0)
                        enddata = fin.read()

                with open(in_file, 'r+b') as fin:
                    fin.seek(NVTPACK_FW_HDR2_size + (part_nr * 12), 0)
                    fin.seek(4, 1)
                    
                    newalignsize = (4 - ((len(replacedata) + is_replace_offset)%4))
                    if newalignsize == 4:
                        newalignsize = 0
                    newsize = len(replacedata) + is_replace_offset + newalignsize
                    
                    if part_nr + 1 < partitions_count:
                        sizediff = newsize - (part_startoffset[part_nr + 1] - part_startoffset[part_nr])
                    else:
                        sizediff = newsize - part_size[part_nr]

                    fin.write(struct.pack('<I', newsize - newalignsize))
                    part_size[part_nr] = newsize - newalignsize
                    fin.seek(4, 1)

                    a = part_nr + 1
                    while(a < partitions_count):
                        fin.write(struct.pack('<I', part_startoffset[a] + sizediff))
                        part_startoffset[a] = part_startoffset[a] + sizediff
                        fin.seek(8, 1)
                        a += 1

                    fin.seek(part_startoffset[part_nr] + is_replace_offset, 0)
                    fin.write(replacedata)

                    for b in range(newalignsize):
                        fin.write(struct.pack('B', 0))

                    if part_nr + 1 < partitions_count:
                        fin.write(enddata)
                    fin.truncate()

                filesize = os.path.getsize(in_file)
                with open(in_file, 'r+b') as fin:
                    fin.seek(28, 0)
                    fin.write(struct.pack('<I', filesize))
                    total_file_size = filesize

                    if part_type[part_nr][:13] == '\033[93mCKSM\033[0m':
                        fin.seek(part_startoffset[part_nr] + 0x14, 0)
                        fin.write(struct.pack('<I', newsize - is_replace_offset))
                return

            if (FW_HDR == 1) | ((FW_HDR == 0) & (partitions_count == 1)):
                with open(in_file, 'rb') as fin:
                    if part_nr + 1 < partitions_count:
                        fin.seek(part_startoffset[part_nr + 1], 0)
                        enddata = fin.read()

                if part_id[part_nr] != 0:
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_size[0] + 28 + ((part_nr - 1) * 12), 0)
                        fin.seek(4, 1)
                        
                        newalignsize = (4 - ((len(replacedata) + is_replace_offset)%4))
                        if newalignsize == 4:
                            newalignsize = 0
                        newsize = len(replacedata) + is_replace_offset + newalignsize
                        
                        if part_nr + 1 < partitions_count:
                            sizediff = newsize - (part_startoffset[part_nr + 1] - part_startoffset[part_nr])
                        else:
                            sizediff = newsize - part_size[part_nr]

                        fin.write(struct.pack('<I', newsize - newalignsize))
                        part_size[part_nr] = newsize - newalignsize
                        fin.seek(4, 1)

                        a = part_nr + 1
                        while(a < partitions_count):
                            fin.write(struct.pack('<I', part_startoffset[a] + sizediff))
                            part_startoffset[a] = part_startoffset[a] + sizediff
                            fin.seek(8, 1)
                            a += 1

                        fin.seek(part_startoffset[part_nr] + is_replace_offset, 0)
                        fin.write(replacedata)

                        for b in range(newalignsize):
                            fin.write(struct.pack('B', 0))

                        if part_nr + 1 < partitions_count:
                            fin.write(enddata)
                        fin.truncate()

                    filesize = os.path.getsize(in_file)
                    if FW_BOOTLOADER == 0:
                        total_file_size = filesize

                    with open(in_file, 'r+b') as fin:
                        if part_type[part_nr][:13] == '\033[93mCKSM\033[0m':
                            fin.seek(part_startoffset[part_nr] + 0x14, 0)
                            fin.write(struct.pack('<I', newsize - is_replace_offset))
                    return
                else:
                    # Complex case for partition 0
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_size[0] + 28, 0)
                        
                        newalignsize = (4 - ((len(replacedata) + is_replace_offset)%4))
                        if newalignsize == 4:
                            newalignsize = 0
                        newsize = len(replacedata) + is_replace_offset + newalignsize
                        
                        if part_nr + 1 < partitions_count:
                            sizediff = newsize - (part_startoffset[part_nr + 1] - part_startoffset[part_nr])
                        else:
                            sizediff = newsize - part_size[part_nr]

                        a = 1
                        while(a < partitions_count):
                            fin.write(struct.pack('<I', part_startoffset[a] + sizediff + 28 + (partitions_count - 1)*12))
                            part_startoffset[a] = part_startoffset[a] + sizediff + 28 + (partitions_count - 1)*12
                            fin.seek(8, 1)
                            a += 1

                        if part_nr + 1 < partitions_count:
                            fin.seek(part_size[0], 0)
                            enddata = fin.read()

                        fin.seek(part_startoffset[part_nr] + is_replace_offset, 0)
                        fin.write(replacedata)

                        part_size[part_nr] = newsize - newalignsize

                        for b in range(newalignsize):
                            fin.write(struct.pack('B', 0))

                        if part_nr + 1 < partitions_count:
                            fin.write(enddata)
                        fin.truncate()

                    filesize = os.path.getsize(in_file)
                    total_file_size = filesize

                    with open(in_file, 'r+b') as fin:
                        if part_type[part_nr][:13] == '\033[93mCKSM\033[0m':
                            fin.seek(part_startoffset[part_nr] + 0x14, 0)
                            fin.write(struct.pack('<I', newsize - is_replace_offset))
                    return
            else:
                print('\033[91mError: Could not replace this partition.\033[0m')
                exit(0)
    else:
        print('\033[91mCould not find partiton with ID %i\033[0m' % is_replace)


def fixCRC(partID):
    global partitions_count
    global total_file_size, orig_file_size
    global FW_BOOTLOADER
    
    for a in range(partitions_count):
        if part_id[a] == partID:
            text, calcCRC = GetPartitionInfo(part_startoffset[a], part_size[a], part_id[a], 0)
            
            if part_crc[a] != calcCRC:
                if part_type[a] == 'uboot':
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_startoffset[a] + 0x36E, 0)
                        fin.write(struct.pack('<H', calcCRC))
                    if is_silent != 1:
                        print('Partition ID ' + str(part_id[a]) + ' - \033[94mCRC fixed\033[0m')
                    break
                
                if part_type[a][:17] == '\033[93mMODELEXT\033[0m':
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_startoffset[a] + 0x36, 0)
                        fin.write(struct.pack('<H', calcCRC))
                    if is_silent != 1:
                        print('Partition ID ' + str(part_id[a]) + ' - \033[94mCRC fixed\033[0m')
                    break
                
                if part_type[a][:13] == '\033[93mCKSM\033[0m':
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_startoffset[a] + 0xC, 0)
                        fin.write(struct.pack('<I', calcCRC))
                    if is_silent != 1:
                        print('Partition ID ' + str(part_id[a]) + ' - \033[94mCRC fixed\033[0m')
                    break
                
                if part_type[a][:13] == '\033[93mBCL1\033[0m':
                    if FW_BOOTLOADER == 0:
                        with open(in_file, 'r+b') as fin:
                            fin.seek(part_startoffset[a] + 0x4, 0)
                            fin.write(struct.pack('<H', calcCRC))
                        if is_silent != 1:
                            print('Partition ID ' + str(part_id[a]) + ' - \033[94mCRC fixed\033[0m')
                        break
            else:
                if is_silent != 1:
                    print('Partition ID ' + str(part_id[a]) + ' - fix CRC not required')

    # fix CRC for whole file
    if FW_HDR2 == 1:
        if(total_file_size != orig_file_size):
            print('Firmware file size \033[94m{:,}\033[0m bytes'.format(total_file_size))
        else:
            print('Firmware file size \033[92m{:,}\033[0m bytes'.format(total_file_size))
    
        CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, 0, total_file_size, 0x24)
        if checksum_value == CRC_FW:
            if is_silent != 1:
                print('Firmware file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
        else:
            with open(in_file, 'r+b') as fin:
                fin.seek(0x24, 0)
                fin.write(struct.pack('<I', CRC_FW))
            if is_silent != 1:
                print('Firmware file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (checksum_value, CRC_FW))

    else:
        if FW_HDR == 1:
            if(total_file_size != orig_file_size):
                print('Firmware file size \033[94m{:,}\033[0m bytes'.format(total_file_size))
            else:
                print('Firmware file size \033[92m{:,}\033[0m bytes'.format(total_file_size))

            CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, part_size[0], NVTPACK_FW_HDR_AND_PARTITIONS_size, 0x14)
            if checksum_value == CRC_FW:
                if is_silent != 1:
                    print('NVTPACK_FW_HDR + Partitions table ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
            else:
                with open(in_file, 'r+b') as fin:
                    fin.seek(part_size[0] + 0x14, 0)
                    fin.write(struct.pack('<I', CRC_FW))
                if is_silent != 1:
                    print('NVTPACK_FW_HDR + Partitions table ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (checksum_value, CRC_FW))
        else:
            if FW_BOOTLOADER == 1:
                total_file_size = os.path.getsize(in_file)
                if(total_file_size != orig_file_size):
                    print('Bootloader file size \033[94m{:,}\033[0m bytes'.format(total_file_size))
                else:
                    print('Bootloader file size \033[92m{:,}\033[0m bytes'.format(total_file_size))
    
                CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, 0, total_file_size, 0x32)
                if checksum_value == CRC_FW:
                    if is_silent != 1:
                        print('Bootloader file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
                else:
                    with open(in_file, 'r+b') as fin:
                        fin.seek(0x32, 0)
                        fin.write(struct.pack('<H', CRC_FW))
                    if is_silent != 1:
                        print('Bootloader file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (checksum_value, CRC_FW))


def main():
    global in_file
    global out_file
    in_file, is_extract, is_extract_offset, is_extract_all, is_replace, is_replace_offset, is_replace_file, is_uncompress, is_uncompress_offset, is_compress, fixCRC_partID = get_args()
    global partitions_count
    global FW_HDR
    global FW_HDR2
    global FW_BOOTLOADER
    global NVTPACK_FW_HDR2_size
    global total_file_size, orig_file_size
    global checksum_value
    global NVTPACK_FW_HDR_AND_PARTITIONS_size
    global workdir

    if platform.system() == 'Windows':
        os.system('color')

    if is_silent != 1:
        ShowInfoBanner()

    if not os.path.exists(in_file):
        print('\033[91m%s input file does not found, exit\033[0m' % in_file)
        exit(0)

    partitions_count = 0
    
    FW_HDR = 0
    FW_HDR2 = 0
    FW_BOOTLOADER = 0

    # OPTIMIZED: Read header only once
    with open(in_file, 'rb') as fin:
        header = fin.read(256)  # Read enough for initial checks
    
    # NVTPACK_FW_HDR2 GUID check
    if struct.unpack('<I', header[0:4])[0] == 0xD6012E07:
        if struct.unpack('<H', header[4:6])[0] == 0x10BC:
            if struct.unpack('<H', header[6:8])[0] == 0x4F91:
                if struct.unpack('>H', header[8:10])[0] == 0xB28A:
                    if struct.unpack('>I', header[10:14])[0] == 0x352F8226:
                        if struct.unpack('>H', header[14:16])[0] == 0x1A50:
                            FW_HDR2 = 1

    if FW_HDR2 != 1:
        print("\033[91mNVTPACK_FW_HDR2\033[0m not found")
        
        if struct.unpack('>I', header[0:4])[0] == 0x42434C31:  # BCL1
            with open(in_file, 'rb') as fin:
                part_startoffset.append(0)
                fin.seek(0xC, 0)
                part_size.append(struct.unpack('>I', fin.read(4))[0] + 0x10)
                part_id.append(0)
                part_endoffset.append(0 + part_size[0])

                fin.seek(part_size[0], 0)
                FW_HDR = 0
                
                if (fin.tell() + 0x10) < os.stat(in_file).st_size:
                    hdr_check = fin.read(16)
                    if struct.unpack('<I', hdr_check[0:4])[0] == 0x8827BE90:
                        if struct.unpack('<H', hdr_check[4:6])[0] == 0x36CD:
                            if struct.unpack('<H', hdr_check[6:8])[0] == 0x4FC2:
                                if struct.unpack('>H', hdr_check[8:10])[0] == 0xA987:
                                    if struct.unpack('>I', hdr_check[10:14])[0] == 0x73A8484E:
                                        if struct.unpack('>H', hdr_check[14:16])[0] == 0x84B1:
                                            FW_HDR = 1
                
                if FW_HDR == 0:
                    print("\033[91mNVTPACK_FW_HDR\033[0m not found")
                    partitions_count = 1
                else:
                    if is_silent != 1:
                        print("\033[93mNVTPACK_FW_HDR\033[0m found")
                    NVTPACK_FW_HDR_AND_PARTITIONS_size = struct.unpack('<I', hdr_check[16:20])[0] if len(hdr_check) > 16 else 0
                    
                    fin.seek(part_size[0] + 0x10, 0)
                    hdr_data = fin.read(12)
                    NVTPACK_FW_HDR_AND_PARTITIONS_size = struct.unpack('<I', hdr_data[0:4])[0]
                    checksum_value = struct.unpack('<I', hdr_data[4:8])[0]
                    partitions_count = struct.unpack('<I', hdr_data[8:12])[0] + 1

                    print('Found \033[93m%i\033[0m partitions' % (partitions_count))

                    total_file_size = os.path.getsize(in_file)
                    orig_file_size = total_file_size
                    print('Firmware file size \033[93m{:,}\033[0m bytes'.format(total_file_size))

                    if (is_extract == -1 & is_replace == -1 & is_uncompress == -1 & is_compress == -1):
                        CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, part_size[0], NVTPACK_FW_HDR_AND_PARTITIONS_size, 0x14)
                        if checksum_value == CRC_FW:
                            print('NVTPACK_FW_HDR + Partitions table ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
                        else:
                            print('NVTPACK_FW_HDR + Partitions table ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m' % (checksum_value, CRC_FW))

                    fin.seek(part_size[0] + 0x1C, 0)

                    for a in range(partitions_count):
                        if a == 0:
                            continue
                        part_data = fin.read(12)
                        part_startoffset.append(struct.unpack('<I', part_data[0:4])[0])
                        part_size.append(struct.unpack('<I', part_data[4:8])[0])
                        part_id.append(struct.unpack('<I', part_data[8:12])[0])
                        part_endoffset.append(part_startoffset[a] + part_size[a])

            for a in range(partitions_count):
                GetPartitionInfo(part_startoffset[a], part_size[a], part_id[a])
        else:
            print("\033[91mBCL1\033[0m not found")

            # Check for bootloader
            first2bytes = struct.unpack('>H', header[0:2])[0]
            if first2bytes == 0x2800:
                with open(in_file, 'rb') as fin:
                    fin.seek(2, 0)
                    boot_hdr = fin.read(30)
                    read1 = struct.unpack('>H', boot_hdr[0:2])[0]
                    read2 = struct.unpack('>H', boot_hdr[4:6])[0]
                    BCL1_offset = struct.unpack('<I', boot_hdr[6:10])[0]
                    constant = struct.unpack('>I', boot_hdr[10:14])[0]
                    read3 = struct.unpack('>H', boot_hdr[16:18])[0]
                    fin.seek(0x30, 0)
                    read55AA = struct.unpack('>H', fin.read(2))[0]
                    
                    if read1 == read2 and read1 == read3 and constant == 0x000580E0 and read55AA == 0x55AA:
                        print('Input file detects as \033[93mBOOTLOADER\033[0m')
                        FW_BOOTLOADER = 1

                        part_startoffset.append(BCL1_offset)
                        fin.seek(BCL1_offset + 0xC, 0)
                        part_size.append(struct.unpack('>I', fin.read(4))[0] + 0x10)
                        part_id.append(0)
                        part_endoffset.append(BCL1_offset + part_size[0])

                        fin.seek(0x24, 0)
                        orig_file_size = struct.unpack('<I', fin.read(4))[0]
                        total_file_size = os.path.getsize(in_file)
                        print('Bootloader required file size \033[93m{:,}\033[0m bytes'.format(orig_file_size), end='')
                        if(total_file_size != orig_file_size):
                            print(', this file size \033[94m{:,}\033[0m bytes'.format(total_file_size))
                        else:
                            print(', this file size \033[92m{:,}\033[0m bytes'.format(total_file_size))

                        fin.seek(0x32, 0)
                        checksum_value = struct.unpack('<H', fin.read(2))[0]
                        
                        if (is_extract == -1 & is_replace == -1 & is_uncompress == -1 & is_compress == -1):
                            CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, 0, orig_file_size, 0x32)
                            if checksum_value == CRC_FW:
                                print('Bootloader file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
                            else:
                                print('Bootloader file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m' % (checksum_value, CRC_FW))

                        bootpart, somecrc = GetPartitionInfo(BCL1_offset, 0, 0)
                        if bootpart != '':
                            partitions_count = 1
                    else:
                        exit(0)
            else:
                exit(0)

    if FW_HDR2 == 1:
        if is_silent != 1:
            print("\033[93mNVTPACK_FW_HDR2\033[0m found")

        with open(in_file, 'rb') as fin:
            fin.seek(16, 0)
            hdr2_data = fin.read(20)
            
            if struct.unpack('<I', hdr2_data[0:4])[0] == 0x16071515:
                if is_silent != 1:
                    print("\033[93mNVTPACK_FW_HDR2_VERSION\033[0m found")
            else:
                print("\033[91mNVTPACK_FW_HDR2_VERSION\033[0m not found")
                exit(0)
            
            NVTPACK_FW_HDR2_size = struct.unpack('<I', hdr2_data[4:8])[0]
            partitions_count = struct.unpack('<I', hdr2_data[8:12])[0]
            total_file_size = struct.unpack('<I', hdr2_data[12:16])[0]
            orig_file_size = total_file_size
            checksum_method = struct.unpack('<I', hdr2_data[16:20])[0]
            
            fin.seek(32, 0)
            checksum_value = struct.unpack('<I', fin.read(4))[0]
            
            print('Found \033[93m%i\033[0m partitions' % partitions_count)
            print('Firmware file size \033[93m{:,}\033[0m bytes'.format(total_file_size))

            if (is_extract == -1 & is_replace == -1 & is_uncompress == -1 & is_compress == -1):
                CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, 0, total_file_size, 0x24)
                if checksum_value == CRC_FW:
                    print('Firmware file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
                else:
                    print('Firmware file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m' % (checksum_value, CRC_FW))

            fin.seek(NVTPACK_FW_HDR2_size, 0)

            for a in range(partitions_count):
                part_data = fin.read(12)
                part_startoffset.append(struct.unpack('<I', part_data[0:4])[0])
                part_size.append(struct.unpack('<I', part_data[4:8])[0])
                part_id.append(struct.unpack('<I', part_data[8:12])[0])
                part_endoffset.append(part_startoffset[a] + part_size[a])

        for a in range(partitions_count):
            GetPartitionInfo(part_startoffset[a], part_size[a], part_id[a])

    # Extract partition
    if is_extract != -1:
        if is_extract_all != 1:
            partition_extract(is_extract, is_extract_offset)
        else:
            for part_nr in range(partitions_count):
                partition_extract(part_id[part_nr], -1)
        exit(0)

    # Replace partition
    if is_replace != -1:
        partition_replace(is_replace, is_replace_offset, is_replace_file)
        exit(0)

    # Uncompress partition
    if is_uncompress != -1:
        part_nr = -1
        for a in range(partitions_count):
            if part_id[a] == is_uncompress:
                part_nr = a
                break
        
        if part_nr != -1:
            if workdir != '':
                out_file = workdir + '/' + in_file + '-uncomp_partitionID' + str(part_id[part_nr])
            else:
                out_file = in_file + '-uncomp_partitionID' + str(part_id[part_nr])
            
            if is_silent != 1:
                if is_uncompress_offset != -1:
                    print('Uncompress partition ID %i from 0x%08X + 0x%08X to \033[93m%s\033[0m' % (part_id[part_nr], part_startoffset[part_nr], is_uncompress_offset, out_file))
                else:
                    print('Uncompress partition ID %i from 0x%08X to \033[93m%s\033[0m' % (part_id[part_nr], part_startoffset[part_nr], out_file))

            if is_uncompress_offset == -1:
                with open(in_file, 'rb') as fin:
                    fin.seek(part_startoffset[part_nr], 0)
                    FourCC = fin.read(4)
                    if FourCC == b'CKSM':
                        is_uncompress_offset = 0x40
                        if is_silent != 1:
                            print('Auto skip CKSM header: 64 bytes')
                    else:
                        is_uncompress_offset = 0

            uncompress(part_startoffset[part_nr] + is_uncompress_offset, out_file, part_size[part_nr] - is_uncompress_offset)
        else:
            print('\033[91mCould not find partiton with ID %i\033[0m' % is_uncompress)
        exit(0)

    # Compress partition
    if is_compress != -1:
        part_nr = -1
        for a in range(partitions_count):
            if part_id[a] == is_compress:
                part_nr = a
                break
        
        if part_nr != -1:
            if workdir != '':
                in2_file = workdir + '/' + in_file + '-uncomp_partitionID' + str(part_id[part_nr])
            else:
                in2_file = in_file + '-uncomp_partitionID' + str(part_id[part_nr])

            if is_silent != 1:
                print('Compress \033[93m%s\033[0m to partition ID %i at 0x%08X' % (in2_file, part_id[part_nr], part_startoffset[part_nr]))

            compress(part_nr, in2_file)
        else:
            print('\033[91mCould not find partiton with ID %i\033[0m' % is_compress)
        exit(0)

    # Fix CRC
    if fixCRC_partID != -1:
        for a in range(partitions_count):
            if part_crc[a] != part_crcCalc[a]:
                if part_type[a] == 'uboot':
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_startoffset[a] + 0x36E, 0)
                        fin.write(struct.pack('<H', part_crcCalc[a]))
                    part_type[a] += ', \033[94mCRC fixed\033[0m'
                
                if part_type[a][:17] == '\033[93mMODELEXT\033[0m':
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_startoffset[a] + 0x36, 0)
                        fin.write(struct.pack('<H', part_crcCalc[a]))
                    part_type[a] += ', \033[94mCRC fixed\033[0m'
                
                if part_type[a][:13] == '\033[93mCKSM\033[0m':
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_startoffset[a] + 0xC, 0)
                        fin.write(struct.pack('<I', part_crcCalc[a]))
                    part_type[a] += ', \033[94mCRC fixed\033[0m'
                
                if part_type[a][:13] == '\033[93mBCL1\033[0m':
                    if FW_BOOTLOADER == 0:
                        with open(in_file, 'r+b') as fin:
                            fin.seek(part_startoffset[a] + 0x4, 0)
                            fin.write(struct.pack('<H', part_crcCalc[a]))
                        part_type[a] += ', \033[94mCRC fixed\033[0m'

        # Fix whole file CRC
        if FW_HDR2 == 1:
            CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, 0, total_file_size, 0x24)
            if checksum_value == CRC_FW:
                print('Firmware file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
            else:
                with open(in_file, 'r+b') as fin:
                    fin.seek(0x24, 0)
                    fin.write(struct.pack('<I', CRC_FW))
                print('Firmware file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (checksum_value, CRC_FW))
        else:
            if FW_HDR == 1:
                CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, part_size[0], NVTPACK_FW_HDR_AND_PARTITIONS_size, 0x14)
                if checksum_value == CRC_FW:
                    print('NVTPACK_FW_HDR + Partitions table ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
                else:
                    with open(in_file, 'r+b') as fin:
                        fin.seek(part_size[0] + 0x14, 0)
                        fin.write(struct.pack('<I', CRC_FW))
                    print('NVTPACK_FW_HDR + Partitions table ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (checksum_value, CRC_FW))
            else:
                if FW_BOOTLOADER == 1:
                    total_file_size = os.path.getsize(in_file)
                    CRC_FW = MemCheck_CalcCheckSum16Bit(in_file, 0, total_file_size, 0x32)
                    if checksum_value == CRC_FW:
                        print('Bootloader file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[92m0x%04X\033[0m' % (checksum_value, CRC_FW))
                    else:
                        with open(in_file, 'r+b') as fin:
                            fin.seek(0x32, 0)
                            fin.write(struct.pack('<H', CRC_FW))
                        print('Bootloader file ORIG_CRC:\033[93m0x%04X\033[0m CALC_CRC:\033[91m0x%04X\033[0m, \033[94mCRC fixed\033[0m' % (checksum_value, CRC_FW))

    # Display partition info
    if partitions_count > 0:
        if len(dtbpart_ID) != 0:
            print(' -------------------------------------------------- PARTITIONS INFO ---------------------------------------------------')
            print('|  ID   NAME            START_OFFSET  END_OFFSET         SIZE       ORIG_CRC   CALC_CRC              TYPE              |')
            print(' ----------------------------------------------------------------------------------------------------------------------')
            for a in range(partitions_count):
                if part_crc[a] == part_crcCalc[a]:
                    print("  %2i    %-15s  0x%08X - 0x%08X     %+11s     0x%04X     \033[92m0x%04X\033[0m     %s" % (part_id[a], dtbpart_name[part_id[a]], part_startoffset[a], part_endoffset[a], '{:,}'.format(part_size[a]), part_crc[a], part_crcCalc[a], part_type[a]))
                else:
                    print("  %2i    %-15s  0x%08X - 0x%08X     %+11s     0x%04X     \033[91m0x%04X\033[0m     %s" % (part_id[a], dtbpart_name[part_id[a]], part_startoffset[a], part_endoffset[a], '{:,}'.format(part_size[a]), part_crc[a], part_crcCalc[a], part_type[a]))
            print(" ----------------------------------------------------------------------------------------------------------------------")
        else:
            print(" -------------------------------------------------- PARTITIONS INFO ---------------------------------------------------")
            print("|  ID   START_OFFSET  END_OFFSET         SIZE       ORIG_CRC   CALC_CRC                        TYPE                    |")
            print(" ----------------------------------------------------------------------------------------------------------------------")
            for a in range(partitions_count):
                if part_crc[a] == part_crcCalc[a]:
                    print("  %2i     0x%08X - 0x%08X     %+11s     0x%04X     \033[92m0x%04X\033[0m     %s" % (part_id[a], part_startoffset[a], part_endoffset[a], '{:,}'.format(part_size[a]), part_crc[a], part_crcCalc[a], part_type[a]))
                else:
                    print("  %2i     0x%08X - 0x%08X     %+11s     0x%04X     \033[91m0x%04X\033[0m     %s" % (part_id[a], part_startoffset[a], part_endoffset[a], '{:,}'.format(part_size[a]), part_crc[a], part_crcCalc[a], part_type[a]))
            print(" ----------------------------------------------------------------------------------------------------------------------")


if __name__ == "__main__":
    main()
