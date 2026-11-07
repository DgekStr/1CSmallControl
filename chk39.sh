#!/bin/bash
echo "  с VPN-сервера:"
timeout 5 bash -c 'cat < /dev/null > /dev/tcp/192.168.0.5/1541' 2>/dev/null && echo "    порт 1541 открыт" || echo "    порт 1541 НЕ открыт"
echo "  резолв srv.1c.dgek.ru: $(getent hosts srv.1c.dgek.ru | awk '{print $1}')"
