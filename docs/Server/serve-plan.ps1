#requires -version 5.1
<#
  Раздаёт страницу плана переезда по HTTP на всех интерфейсах (0.0.0.0) и открывает её в браузере.
  Каждое подключение пишется в консоль (живой лог) и в файл.

  Запуск:        powershell -NoProfile -ExecutionPolicy Bypass -File "E:\_Project\1CSmallControl\docs\Server\serve-plan.ps1"
  Свой лог:      ... -Log "E:\_Project\1CSmallControl\docs\Server\plan-access.log"
  Без браузера:  ... -NoOpen
  Другой порт:   ... -Port 8091
  Остановка:     Ctrl+C
#>
param(
  [int]$Port = 8090,
  [string]$File = "E:\_Project\1CSmallControl\docs\Server\new-server-plan.html",
  [string]$Log = (Join-Path $env:TEMP "plan_server.log"),
  [switch]$NoOpen
)

if (-not (Test-Path $File)) { throw "Файл не найден: $File" }

# --- Python: py launcher, python в PATH, bundled-сборка DSH ---
$py = $null
foreach ($cand in @(
    'py',
    'python',
    (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
    'C:\Users\DgekStr\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
  )) {
  if ($cand -and (Get-Command $cand -ErrorAction SilentlyContinue)) { $py = (Get-Command $cand).Source; break }
}
if (-not $py) { throw "Python не найден. Установите Python 3 или укажите путь вручную." }

$root = Split-Path -Parent $File
$name = Split-Path -Leaf $File
$logPath = [IO.Path]::GetFullPath($Log)

$serverCode = @"
import http.server, os, socketserver
from datetime import datetime

ROOT = r"$root"
FILE = "$name"
PORT = $Port
LOG = r"$logPath"

def log(line):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass

class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html", "/plan", "/plan.html"):
            self.path = "/" + FILE
        return super().do_GET()
    def log_message(self, fmt, *args):
        ua = self.headers.get("User-Agent", "")[:90]
        log("%s  %-15s  %s  [%s]" % (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            self.address_string(),
            fmt % args,
            ua))

os.chdir(ROOT)
socketserver.ThreadingTCPServer.allow_reuse_address = True
with socketserver.ThreadingTCPServer(("0.0.0.0", PORT), Handler) as httpd:
    log("%s  START  serving %s on http://0.0.0.0:%d/" % (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"), FILE, PORT))
    httpd.serve_forever()
"@

$tmp = Join-Path $env:TEMP ("plan_server_{0}.py" -f $Port)
[IO.File]::WriteAllText($tmp, $serverCode, (New-Object System.Text.UTF8Encoding($false)))

Write-Host ("Страница: {0}" -f $File) -ForegroundColor DarkGray
Write-Host ("Лог:      {0}" -f $logPath) -ForegroundColor DarkGray
Write-Host ("  локально: http://127.0.0.1:{0}/" -f $Port) -ForegroundColor Green
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } |
  ForEach-Object { Write-Host ("  по сети:  http://{0}:{1}/" -f $_.IPAddress, $Port) }
Write-Host "Живой лог — ниже. Остановить: Ctrl+C" -ForegroundColor DarkGray

if (-not $NoOpen) {
  $browser = 'C:\Program Files\Yandex\YandexBrowser\Application\browser.exe'
  if (Test-Path $browser) { Start-Process $browser -ArgumentList ("http://127.0.0.1:{0}/" -f $Port) }
  else { Start-Process ("http://127.0.0.1:{0}/" -f $Port) }
}

try {
  & $py $tmp
} finally {
  Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  Write-Host "Сервер остановлен" -ForegroundColor Yellow
}