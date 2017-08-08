ECHO install chocolatey
@powershell -NoProfile -ExecutionPolicy Bypass -Command "iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))" && SET "PATH=%PATH%;%ALLUSERSPROFILE%\chocolatey\bin"

ECHO install programming languages
choco install -vy golang python2 nodejs 

ECHO install apps and tools
choco install -vy chrome mobaxterm slack winrar utorrent git sysinternals filezilla curl fiddler windirstat docker mingw visualstudiocode spotify
npm install -g yo typings typescript generator-swell
