Media Host setup 1.6
====================

Answer two questions (catalog PC vs file server, Windows vs Linux).
The page scans the LAN and tells you what to install where.

Windows
  Double-click INSTALL.bat (or ..\INSTALL.bat).
  If Python is missing, the official embeddable 3.12 build is downloaded.

Linux or macOS media server
  chmod +x INSTALL.sh && ./INSTALL.sh

Then click "Set up this host" if this machine holds the disks. The page
matches Media Comparator (dark canvas, teal accent). It installs:

  • ffprobe          — deep scan / quality
  • CrystalDiskInfo  — Windows SMART (or smartctl on Linux)
  • Firewall rule    — TCP 8766 (Windows shows a Yes/No Admin prompt;
                       click Yes, or run OPEN_FIREWALL.bat)
  • Agent            — scan + probe + SMART + delete API

Copy the address shown into Comparator → Add drive → media host.

Layouts
  Linux catalog + Windows file server
  Linux catalog + Linux media server
  Windows catalog + Windows file server
  Windows catalog + Linux file server
  Mac catalog + Windows or Linux host
  Everything on one computer (no agent)
