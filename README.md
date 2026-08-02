# CHODE - Chad Code CLI (v0.5.0 Cross-Platform)

> **Your own open-source, provider-agnostic AI coding assistant running in your terminal.**  
> Works with Anthropic Claude, OpenAI, DeepSeek, Google Gemini, xAI Grok, Ollama (100% offline local models), LM Studio, and OpenRouter. Fully cross-platform on **macOS**, **Linux**, and **Windows**.

---

## Key Features

- **Universal Cross-Platform Shell**:
  - **macOS / Linux**: Executes native `bash` or `zsh` subshells.
  - **Windows**: Executes `PowerShell` or `cmd.exe`.
- **Multi-Provider AI Brain**:
  - Native support for Anthropic Claude (3.5 Sonnet / Opus / Haiku), OpenAI (GPT-4o), DeepSeek (V3 / R1), Google Gemini, xAI Grok, and OpenRouter.
  - Local & Offline LLM support via Ollama, LM Studio, llama.cpp, and vLLM.
- **Agentic Tool Loop**:
  - Read, write, and surgical edit files with diff previews and safety undo checkpoints.
  - Interactive bash execution, file search (glob/grep), web fetch, and todo task management.
- **Model Context Protocol (MCP)**:
  - Connect external MCP tools over `stdio` and `http`.
- **In-Terminal Splash Cinema**:
  - Optional ASCII/ANSI terminal video playback on launch powered by `ffmpeg` or `mpv`.

---

## Idiot-Proof Quick Start Guide

### Step 1: Install Python 3.9+

- **macOS**:
  ```bash
  python3 --version
  # If not installed: brew install python3
  ```
- **Linux**:
  ```bash
  python3 --version
  # If not installed: sudo apt install python3 python3-pip
  ```
- **Windows**:
  Download from [python.org](https://www.python.org/downloads/). Check the box **"Add python.exe to PATH"**.

### Step 2: Clone & Install Dependency

```bash
git clone https://github.com/chchchadzilla/chode.git
cd chode
pip install requests
```

### Step 3: Launch CHODE

- **Universal Launcher (macOS / Linux / Windows)**:
  ```bash
  python3 chode-launcher.py
  ```
- **macOS / Linux Shell Shortcut**:
  ```bash
  ./chode-start
  ```
- **Windows Batch Shortcut**:
  ```cmd
  chode-start.bat
  ```

---

## Configuration & Setup Wizard

On first launch, select **Setup Wizard** from the menu. It will guide you through:
1. Choosing your preferred AI provider (Anthropic, OpenAI, DeepSeek, Ollama, OpenRouter).
2. Entering your API Key (stored locally in `~/.chode/config.json`).
3. Testing live model connectivity.

---

## License & Author
Created by **Chad Keith** ([@chchchadzilla](https://github.com/chchchadzilla)).  
Licensed under the **MIT License**.
