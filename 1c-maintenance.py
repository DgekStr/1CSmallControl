#!/usr/bin/env python3
"""CLI регламентных работ: запуск и завершение из скриптов и по таймеру.

Примеры:
  1c-maintenance start --minutes 40 --comment "обновление 3.0.205.22" --tune
  1c-maintenance stop --reason "обновление завершено"
  1c-maintenance tick
  1c-maintenance status
"""
import argparse
import json
import os
import sys

sys.path.insert(0, '/opt/1c-portal')
os.environ.setdefault('PORTAL_DB', '/opt/1c-portal/portal.db')

import maintenance  # noqa: E402


def main():
    parser = argparse.ArgumentParser(prog='1c-maintenance')
    sub = parser.add_subparsers(dest='command')

    p_start = sub.add_parser('start', help='начать работы немедленно')
    p_start.add_argument('--minutes', type=int, default=30)
    p_start.add_argument('--comment', default='')
    p_start.add_argument('--author', default='cli')
    p_start.add_argument('--message', default='')
    p_start.add_argument('--tune', action='store_true', help='включить ускорение PostgreSQL')

    p_stop = sub.add_parser('stop', help='завершить работы')
    p_stop.add_argument('--reason', default='вручную')

    sub.add_parser('tick', help='обработка по таймеру')
    sub.add_parser('status', help='текущее состояние')

    args = parser.parse_args()
    maintenance.init()

    if args.command == 'start':
        ok, message = maintenance.start_now(args.minutes, args.comment, args.author,
                                            tune=args.tune, message=args.message)
        print(message)
        return 0 if ok else 1

    if args.command == 'stop':
        ok, message = maintenance.stop_now(args.reason)
        print(message)
        return 0 if ok else 1

    if args.command == 'tick':
        result = maintenance.tick()
        print(result or 'ok')
        return 0

    if args.command == 'status':
        print(json.dumps(maintenance.state(), ensure_ascii=False))
        return 0

    parser.print_help()
    return 64


if __name__ == '__main__':
    sys.exit(main())
