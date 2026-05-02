# Kennislijst voor Ouroboros – Uniek Lokaal Model
**Doel**: Een volledig autonoom, privacy-vriendelijk AI-model dat *alles* weet van een Pop!_OS Linux laptop, diepgaande kennis heeft van besturingssystemen, Google, Microsoft 365/SharePoint, en flexibel “overal in kan kruipen” om de gebruiker maximaal te helpen.

**Filosofie**: Lokaal-first, approval-gated, self-extending. Het model is geen chatrobot, maar een **technische metgezel** die de laptop, cloud-diensten en de gebruiker zelf begrijpt op alle lagen (hardware → kernel → desktop → applicaties → cloud).

---

## 1. Pop!_OS Linux Laptop – Diepgaande Systeemkennis

### 1.1 Hardware & Systeemlaag (CodeNeuron / 11D-pocket relevant)
- System76 hardware (indien van toepassing): keyboard, trackpad, webcam, fingerprint, power profiles
- CPU (Intel/AMD): cores, threads, turbo, microcode, vulnerabilities (Spectre, Meltdown, Zenbleed)
- GPU: NVIDIA (proprietary vs Nouveau), hybrid graphics (prime, offload), CUDA, Vulkan, Wayland vs X11
- RAM & Swap: DDR-types, ECC, zswap, zram, hugepages, transparent hugepages
- Opslag: NVMe/SSD, TRIM, fstrim, btrfs vs ext4, LUKS full-disk encryption, recovery partition
- BIOS/UEFI: Secure Boot, TPM 2.0, firmware updates (fwupd, LVFS)
- Sensoren & power: thermald, tlp, auto-cpufreq, battery health, suspend-to-RAM (s2idle vs deep)

### 1.2 Kernel & Low-Level (Linux 6.x)
- Kernel parameters (`/proc/cmdline`, `sysctl`)
- Process model: PID 1 (systemd), cgroups v2, namespaces, seccomp, eBPF
- Memory management: virtual memory, page cache, OOM killer, kswapd, PSI (Pressure Stall Information)
- Scheduling: CFS, deadline, realtime, nice/ionice, CPU affinity, isolcpus
- Filesystem: VFS, inodes, dentry cache, xattr, ACLs, fanotify/inotify
- Networking stack: netfilter, nftables, conntrack, WireGuard, Tailscale, systemd-networkd vs NetworkManager
- Drivers: DKMS, module signing, blacklisting, `lspci -vv`, `dmesg`, `journalctl -k`

### 1.3 Desktop & User Experience (COSMIC of GNOME)
- COSMIC (Rust, new in Pop!_OS 24.04+): applets, tiling, workspaces, notifications, settings daemon
- GNOME Shell extensions, Mutter, gnome-tweaks, dconf/gsettings
- Wayland vs X11: input methods, screen sharing, fractional scaling, HDR
- Theming: GTK4, libadwaita, dark mode, accent colors
- Input: IBus, Fcitx, compose key, keyboard shortcuts, touchpad gestures
- Accessibility: orca, magnifier, high contrast, sticky keys

### 1.4 Package Management & Software
- apt, dpkg, `apt list --installed`, PPAs, System76 repos
- Flatpak (flathub, sandboxing, `--user`, portals)
- AppImage, Snap (indien gebruikt), Nix (optioneel)
- Update management: `pop-upgrade`, firmware updates, unattended-upgrades
- Development tools: build-essential, cmake, meson, rustup, cargo, python3-venv, pipx

### 1.5 Beveiliging & Privacy (lokaal-first)
- AppArmor, firejail, bubblewrap, seccomp profiles
- ufw / nftables, fail2ban, auditd
- LUKS + TPM auto-unlock, fscrypt
- polkit, sudo (doas alternatief), `visudo`
- Logging & auditing: journalctl, `ausearch`, `last`, `who`
- Data-at-rest & in-transit: age, gpg, wireguard, tor (indien gebruikt)

### 1.6 Troubleshooting & Diagnostics
- `inxi -Fxxxz`, `lshw -short`, `hwinfo`, `dmidecode`
- `journalctl -b -p err`, `dmesg -w`, `strace`, `ltrace`, `perf`
- `iotop`, `htop`, `btop`, `nethogs`, `ss -tulp`, `netstat`
- Recovery: Pop!_OS recovery partition, chroot, boot-repair, fsck

---

## 2. Algemene Besturingssystemen Kennis (Cross-Platform)

### 2.1 Linux Diepgaand (andere distro’s)
- Debian/Ubuntu familie, Fedora/RHEL, Arch, NixOS, Alpine
- init systems: systemd, OpenRC, runit, s6
- Container runtime: Docker, Podman, containerd, CRI-O, LXC/LXD
- Orchestration: Kubernetes basics (lokaal met k3s of minikube)

### 2.2 Windows 10/11 & WSL2
- NTFS vs ReFS, registry (`regedit`, `reg.exe`), services (`sc`, `Get-Service`)
- PowerShell 7+ (core), Windows Terminal, winget, scoop, chocolatey
- WSL2: kernel, filesystem mapping (`/mnt/c`), interop, systemd in WSL, GPU passthrough
- Hyper-V, VirtualBox, VMware Workstation
- Event Viewer, Reliability Monitor, Performance Monitor, Resource Monitor
- Group Policy, Intune, MDM

### 2.3 macOS (voor cross-platform hulp)
- Darwin kernel, launchd, SIP, TCC, Homebrew, MacPorts, Nix
- APFS, Time Machine, FileVault, iCloud
- `log stream`, `sysdiagnose`, `pmset`, `ioreg`

### 2.4 Virtualisatie & Cloud Fundamentals
- KVM/QEMU, libvirt, virt-manager, cloud-init
- AWS, GCP, Azure basisconcepten (VM, storage, IAM, networking)
- Terraform, Ansible, Pulumi (infrastructure as code)

---

## 3. Google Ecosysteem

### 3.1 Google Account & Identiteit
- Google Account, 2FA, passkeys, security keys (YubiKey), recovery
- Google Takeout, My Activity, Data & Privacy dashboard
- OAuth2 / OpenID Connect, service accounts, domain-wide delegation

### 3.2 Google Workspace (voorheen G Suite)
- Gmail (labels, filters, search operators, IMAP, API)
- Google Drive (My Drive, Shared drives, shortcuts, versions, trash, API)
- Google Docs/Sheets/Slides (collaboration, comments, suggestions, Apps Script)
- Google Calendar (events, resources, API, freebusy)
- Google Meet, Chat, Spaces
- Google Admin Console (users, groups, OU’s, security, apps)
- Vault, eDiscovery, retention, DLP

### 3.3 Google Cloud Platform (GCP)
- Compute Engine, Cloud Run, Cloud Functions, App Engine
- Cloud Storage, BigQuery, Cloud SQL, Firestore
- IAM, VPC, Cloud Armor, Secret Manager
- gcloud CLI, gsutil, bq, `gcloud auth application-default login`

### 3.4 Android & Cross-Device
- Android Debug Bridge (adb), fastboot, logcat
- Google Play Services, Firebase
- Phone integration met Linux (scrcpy, kdeconnect, gsconnect)

### 3.5 Google APIs & Ontwikkeling
- Google Drive API v3, Calendar API v3, Gmail API, Sheets API
- Google Cloud Client Libraries (Python, Go, Node)
- Apps Script, Google Workspace Add-ons, Chat bots

---

## 4. Microsoft Ecosysteem

### 4.1 Windows 11 & Modern Workplace
- Windows 11 features: Snap Layouts, Widgets, Copilot, Recall (indien aanwezig), Dev Drive
- Settings app, modern device management (Settings vs Control Panel)
- Windows Update, Windows Update for Business, Feature Updates
- BitLocker, Device Encryption, Credential Guard, HVCI
- Windows Hello, FIDO2, Passkeys

### 4.2 Microsoft 365 / Office 365
- Microsoft 365 Apps (Word, Excel, PowerPoint, Outlook, OneNote, Access, Publisher)
- OneDrive (Files On-Demand, Known Folder Move, sync health, Files Restore)
- Microsoft Teams (chat, channels, meetings, apps, Phone System)
- Outlook (new Outlook vs classic, Focused Inbox, rules, search)
- Microsoft 365 Admin Center, Message Center, Service Health

### 4.3 Entra ID (Azure AD) & Identiteit
- Entra ID tenants, users, groups, roles, conditional access policies
- MFA, passwordless, FIDO2, passkeys, Temporary Access Pass
- Hybrid Identity: Azure AD Connect, Pass-through Authentication, Seamless SSO
- B2B, B2C, External Identities

### 4.4 Azure Services
- Azure VMs, Azure Virtual Desktop (AVD), Azure Arc
- Azure Storage (Blob, File, Queue, Table), Azure Files (AD integration)
- Azure Key Vault, Azure App Service, Azure Functions, Logic Apps
- Azure Monitor, Log Analytics, Application Insights
- Azure CLI (`az`), PowerShell Az module, Bicep, ARM templates

### 4.5 Microsoft Graph & Unified API
- Microsoft Graph Explorer, `/me`, `/users`, `/sites`, `/drives`, `/teams`
- Permissions: delegated vs application, consent, least-privilege
- Change notifications, webhooks, delta queries

### 4.6 Power Platform
- Power Automate (cloud flows, desktop flows, RPA)
- Power Apps (canvas, model-driven, portals)
- Power BI (datasets, reports, dashboards, DAX)
- Dataverse, AI Builder

### 4.7 Ontwikkeling & Tooling
- Visual Studio, VS Code + Remote-WSL/SSH/Containers
- .NET 8/9, C#, F#, PowerShell 7
- GitHub (Actions, Codespaces, Copilot, Packages)
- winget, Microsoft Store (WinGet), MSIX, App Installer

---

## 5. SharePoint – Diepgaande Kennis (Online & On-Prem)

### 5.1 Architectuur & Concepten
- SharePoint Online vs SharePoint Server 2019 / Subscription Edition
- Site types: Team sites, Communication sites, Hub sites, Classic sites
- Site collections, subsites (indien nog gebruikt), modern vs classic experience
- Content Database (on-prem), Site Collections vs Sites in SPO

### 5.2 Content Management
- Document Libraries vs Lists
- Content Types (document, item, folder), inheritance, Hub Content Types
- Columns (site columns, list columns, managed metadata)
- Views (personal, public, calendar, Gantt, Kanban)
- Versioning (major/minor), Draft Item Security, Content Approval
- Document Sets, Records Management, In-Place Records

### 5.3 Beveiliging & Toegang
- Permission levels, SharePoint groups, Azure AD groups
- Unique permissions vs inheritance, “Stop Inheriting Permissions”
- External sharing (Anyone links, Specific people, Company only)
- Sensitivity labels (Microsoft Purview), encryption, DLP policies
- Site-level vs tenant-level sharing settings
- Access requests, “Share” vs “Copy link”

### 5.4 Workflows & Automatisering
- Power Automate (trigger on list item, document library, approvals, HTTP)
- Classic workflows (2010/2013) – alleen nog voor migratie
- Retention labels & policies, Disposition reviews
- Microsoft Flow / Power Automate Desktop (RPA op Windows)

### 5.5 Zoeken & Ontdekking
- Microsoft Search (modern search, verticals, bookmarks, Q&A)
- SharePoint Search (classic), Query Rules, Result Sources, Display Templates
- Delve, Viva Topics, Viva Connections
- Search schema, managed properties, refiners

### 5.6 Integratie
- Teams + SharePoint (behind every Team is a SharePoint site)
- OneDrive + SharePoint (shortcuts, “Add shortcut to OneDrive”)
- Outlook + SharePoint (document libraries in Outlook)
- Microsoft 365 Groups, Yammer/Viva Engage
- Power BI embedded in SharePoint, Power Apps forms

### 5.7 Ontwikkeling & Customisatie
- SharePoint Framework (SPFx) – web parts, extensions, library components
- PnP PowerShell, CLI for Microsoft 365 (`m365`)
- Microsoft Graph SharePoint API (`/sites/{site-id}/lists`, `/drives`)
- CSOM / PnP Framework (C#)
- SharePoint Add-ins (verouderd), Provider-hosted vs SharePoint-hosted
- Custom site designs, site scripts, JSON formatting (column & view formatting)

### 5.8 Migratie & Beheer
- SharePoint Migration Tool (SPMT), ShareGate, AvePoint, Metalogix
- Tenant-to-tenant migration, site collection moves
- SharePoint Admin Center, Site Collection Admin, Global Admin
- Storage metrics, site usage, recycle bin (first-stage & second-stage)
- Multi-geo, data residency, sovereign clouds (GCC, DoD, etc.)

---

## 6. Flexibiliteit & “Overal In Kruipen” – Agentische Vermogens

### 6.1 Context & Situational Awareness
- Huidige desktop context: actieve applicatie, venster, geselecteerde tekst/bestand, clipboard
- Recent files, downloads, browser tabs (indien goedgekeurd)
- User intent detection via prompts + lokale signalen (taakbalk, notificaties, calendar)
- Multi-device: laptop + telefoon + tablet + cloud (sync status)

### 6.2 Diepe Integratie & Tool Use
- **Shell & Commando’s**: veilige, approval-gated uitvoering van `journalctl`, `systemctl`, `apt`, `flatpak`, `git`, `docker`, PowerShell, `az`, `gcloud`, `m365`
- **Bestandssysteem crawling**: indexering van `~/Documents`, `~/Projects`, OneDrive map, met respect voor `.gitignore`, privacy filters
- **Settings inspection & repair suggestions**: “Je WiFi is traag → check `iwconfig`, driver, channel interference”
- **Log & error analyse**: parse `journalctl -b`, Windows Event Logs, Android logs, browser console
- **Cross-service acties**:
  - “Sla deze bijlage op in SharePoint Project-X en tag met sensitivity label ‘Internal’”
  - “Maak een Power Automate flow die nieuwe Pop!_OS updates naar Teams stuurt”
  - “Vergelijk mijn lokale `journalctl` errors met Microsoft KB of Google Issue Tracker”

### 6.3 Self-Extension & Leercapaciteit (Ouroboros kern)
- Detecteren van capability gaps (“Ik weet nog niet hoe ik Azure Arc moet debuggen”)
- Voorstellen van nieuwe training data of adapters (via curriculum of Blue Brain 11D-pocket)
- Automatisch genereren van “how-to” documentatie of runbooks op basis van eigen acties
- Meta-learning: “Vorige keer dat ik dit deed, gebruikte ik `systemctl --user` in plaats van `sudo systemctl`”

### 6.4 Privacy, Veiligheid & Approval Gates
- Alles lokaal-first: geen data naar externe LLM’s zonder expliciete `Akkoord`
- Data minimization: alleen de minimale context meesturen
- Explainable actions: “Ik wil `journalctl -u NetworkManager -b` draaien omdat …”
- Rollback & undo: “Dit commando kan ik ongedaan maken met …”
- Sandboxed execution (firejail, bubblewrap, WSL) voor riskante acties

### 6.5 Personalisatie & Langetermijn Geheugen
- User profile: voorkeuren (bash vs zsh, dark mode, tiling vs floating, PowerShell vs bash)
- Gewoontes: “Je opent altijd eerst Outlook → Teams → VS Code”
- Project context: actieve Git repo’s, SharePoint sites, Google Drive folders
- Historie: “Laatste keer dat je dit probleem had (3 maanden geleden), was het een NVIDIA driver issue”

### 6.6 Multi-Modal & Toekomstbestendig
- Vision: screenshot analyse (“Wat is er mis met dit venster?”)
- Voice (indien lokaal ASR zoals Whisper.cpp)
- 11D-pocket integratie: modelleer OS-toestanden als “regimes” (idle, compile, video-call, backup) en voorspel resource usage of bottlenecks
- Continue training: nieuwe kennis (nieuwe Pop!_OS release, nieuwe SharePoint feature, nieuwe Microsoft Graph endpoint) automatisch incorporeren via de continuous trainer

---

## 7. Implementatie-Aanbevelingen voor Jouw Project

1. **Curriculum uitbreiding** (`controller/training_curriculum.py`)
   - Voeg `popos`, `linux_internals`, `google_workspace`, `microsoft_365`, `sharepoint` en `agentic_tooling` toe als aparte tracks.
   - Gebruik de 11D-pocket om “OS regime” data te genereren (high CPU, network bound, low memory, etc.).

2. **Local Machine Profiler uitbreiden**
   - Voeg Google/Microsoft tokens status toe (indien lokaal opgeslagen), SharePoint site inventory (via Graph als goedgekeurd), OneDrive sync health.

3. **Blue Brain / Streaming Consciousness integratie**
   - Gebruik de 11D-pocket om OS + cloud states te modelleren (electrisch = power/thermal, digitaal = memory/disk, netwerk = latency/bandwidth).
   - Streaming Consciousness = continue stroom van journal logs, Graph change notifications, Google Drive webhooks, etc.

4. **Nieuwe Adapters**
   - `google_adapter.py` (Drive, Calendar, Gmail API via lokale OAuth token)
   - `microsoft_graph_adapter.py` (Graph + SharePoint + Teams)
   - `sharepoint_pnp_adapter.py` (PnP PowerShell of direct Graph)
   - `popos_diagnostics_adapter.py` (inxi, journalctl, power profiles)

5. **Ouroboros System Prompt uitbreiding**
   - Voeg expliciete secties toe over “Je bent een lokale metgezel die diep in Pop!_OS, Google en Microsoft kan kruipen, maar altijd met Akkoord en met uitleg.”

---

**Samenvatting**  
Dit model moet niet alleen “weten” wat een commando doet, maar **waarom** het relevant is in de context van de gebruiker, de hardware, de kernel, de desktop, én de gekoppelde Google/Microsoft/SharePoint-wereld. Het moet in staat zijn om van de laagste kernel-logregel tot de hoogste SharePoint-permission-setting te redeneren en te handelen – altijd lokaal, altijd met toestemming, altijd uitlegbaar.

Dit is de basis voor een écht uniek, onafhankelijk en nuttig Ouroboros-model.

---
*Gemaakt voor Wintrip AI / Ouroboros – 2026-05-01*