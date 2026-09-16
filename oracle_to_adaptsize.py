#!/usr/bin/env python3
import argparse
import struct
import sys

REC = struct.Struct('<IQIq')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='-', help="raw OracleGeneral input, '-' for stdin")
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    src = sys.stdin.buffer if args.input == '-' else open(args.input, 'rb')
    n = 0
    try:
        with open(args.output, 'w', buffering=1024 * 1024) as out:
            buf = b''
            while True:
                chunk = src.read(8 * 1024 * 1024)
                if not chunk:
                    break
                buf += chunk
                usable = (len(buf) // REC.size) * REC.size
                for ts, obj, size, _ in struct.iter_unpack(REC.format, buf[:usable]):
                    if size <= 0:
                        size = 1
                    out.write(f'{ts} {obj} {size}\n')
                    n += 1
                buf = buf[usable:]
            if buf:
                raise SystemExit(f'partial OracleGeneral record: {len(buf)} bytes')
    finally:
        if src is not sys.stdin.buffer:
            src.close()
    print(f'converted {n} OracleGeneral requests -> {args.output}', file=sys.stderr)


if __name__ == '__main__':
    main()
