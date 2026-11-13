# Setting up the Mac mini

A weekend walkthrough for giving the bot a voice: a local AI model on your Mac
mini that plays the trader, writes a daily diary, makes his own (never placed)
picks, and keeps notes to himself. Everything here is free. Allow about 90
minutes, most of it waiting for downloads.

**What the Mac mini does and does not do**

- It does **not** trade. The trading bot keeps running on Fly.io exactly as
  now, and it never waits on the Mac mini.
- It reads the bot's memory from GitHub, runs the model, and saves the
  trader's writing back to GitHub.
- If the Mac mini is off, the only thing missing is that day's diary.

Every command below goes in the **Terminal** app on the Mac mini (press
Command-Space, type "Terminal", press Return). Paste one line at a time.

---

## The short version (three pastes)

For our Mac mini (Apple M4 Pro, 24 GB memory, 512 GB disk) the setup script
does almost everything. It picks `gpt-oss:20b`, a 14 GB download that leaves
about 10 GB of memory free while it runs.

1. Install Homebrew. It asks for the Mac's password, installs Apple's
   command-line tools along the way, and prints two "Next steps" lines at the
   end: paste those too.

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. Download the project (it is public, so no sign-in is needed yet):

   ```bash
   git clone https://github.com/jones-benjam/alpaca-options-bot.git ~/alpaca-options-bot
   ```

3. Run the setup. It takes 15 to 40 minutes, mostly the model download, and
   stops once to sign you in to GitHub in the browser:

   ```bash
   ~/alpaca-options-bot/mac_mini/setup.sh
   ```

When it prints DONE, do the two **Energy** settings in Part 2 below, and the
optional keys in Part 6. That is the whole setup. To see what the script would
do without changing anything, add `--dry-run`.

**Then experiment:**

| Try this | Command (from `~/alpaca-options-bot`) |
|---|---|
| Talk to him about today's trades | `python3 trader.py chat` |
| Compare models on the same diary request | `ollama pull gemma4:12b`, then `python3 trader.py compare` |
| Try a different personality | Copy `memory/PERSONA.md` to a new name, edit it, set `PERSONA_FILE=` in `mac_mini/config.env`, then `python3 trader.py diary` |
| Chat with him in the Ollama app | `python3 trader.py modelfile`, then follow what it prints |
| Make him think harder or faster | Set `THINK=high` or `THINK=low` in `mac_mini/config.env` |

The rest of this page is the same setup done by hand, for reference and for
fixing problems.

---

## Part 1. Check what the Mac mini can run (5 minutes)

1. Apple menu > **About This Mac**. Write down the **Chip** and **Memory**.
2. It must say Apple M1 or later. An Intel Mac mini is too slow for this.
3. Pick a model from this table. Bigger models write better and make fewer
   mistakes, but must fit in memory with room left for macOS.

| Mac mini memory | Model to use | Download size |
|---|---|---|
| 8 GB | `qwen3.5:4b` | 3.3 GB |
| 16 GB | `qwen3.5:9b` | 6.6 GB |
| 24 GB (ours) | `gpt-oss:20b` | 14 GB |
| 32 GB | `qwen3.5:27b` | 17 GB |
| 48 GB or more | `qwen3.5:35b` | 22 GB |

Two more worth trying on 24 GB: `gemma4:12b` (7.7 GB), smaller and quicker,
and `gemma4:26b-a4b-it-qat` (16 GB), larger but a tight fit, so close every
other app first. `python3 trader.py compare` runs them side by side.

Sizes are from Ollama's model library on Nov 13, 2026. None of these has been
run against this project yet, so treat the first evening as a test. Any model
in Ollama's library works: change one line in `mac_mini/config.env`.

## Part 2. Keep the Mac mini awake and reachable (10 minutes)

In **System Settings**:

1. **Energy**: turn on "Prevent automatic sleeping when the display is off"
   and "Start up automatically after a power failure".
2. **General > Software Update**: install any pending update, then restart.
3. Optional, to use it from your MacBook: **General > Sharing**, turn on
   **Screen Sharing** and **Remote Login**. On the same Wi-Fi you can then
   open it from the MacBook's Finder (Go > Network), or run
   `ssh yourname@your-mac-mini.local` in the MacBook's Terminal.

## Part 3. Install the tools (15 minutes)

1. Apple's command-line tools (gives you `git` and `python3`). A window pops
   up; click Install and wait:

   ```bash
   xcode-select --install
   ```

2. Homebrew, the installer for everything else. It asks for the Mac's
   password and prints two "Next steps" lines at the end; run those too:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

3. Ollama (runs the model) and GitHub's command-line tool:

   ```bash
   brew install ollama gh
   ```

4. Start Ollama and have it start by itself after every restart:

   ```bash
   brew services start ollama
   ```

## Part 4. Download the model (10 to 40 minutes, mostly waiting)

Use the model you picked in Part 1. For our 24 GB Mac mini:

```bash
ollama pull gpt-oss:20b
```

Check that it talks:

```bash
ollama run gpt-oss:20b "In one sentence, what is a put option?"
```

## Part 5. Get the project (10 minutes)

1. Sign in to GitHub. Choose GitHub.com, HTTPS, and "Login with a web
   browser", then follow the prompts:

   ```bash
   gh auth login
   ```

2. Let `git` use that sign-in, then download the project:

   ```bash
   gh auth setup-git
   ```

   ```bash
   gh repo clone jones-benjam/alpaca-options-bot ~/alpaca-options-bot
   ```

3. Tell `git` who is saving changes (use your own name and email):

   ```bash
   git config --global user.name "Your Name"
   ```

   ```bash
   git config --global user.email "you@example.com"
   ```

4. Set the trader's name and model:

   ```bash
   cp ~/alpaca-options-bot/mac_mini/config.env.example ~/alpaca-options-bot/mac_mini/config.env
   ```

   ```bash
   open -e ~/alpaca-options-bot/mac_mini/config.env
   ```

   Change `MODEL=` to the model you downloaded, and `TRADER_NAME=` if you
   want a different name. Save and close.

## Part 6. Optional: give the Mac mini the Alpaca paper keys (5 minutes)

Without the keys, the trader reads whatever GitHub's own daily job last
saved, which can be several hours late. With them, the Mac mini updates the
daily record itself and nothing depends on GitHub's timing. These are the
paper-trading keys; the Mac mini still places no trades.

On the **MacBook**, AirDrop the file `~/alpaca-options-bot/.env` to the Mac
mini (in Finder press Command-Shift-. to show hidden files). On the **Mac
mini**, move it from Downloads into place:

```bash
mv ~/Downloads/.env ~/alpaca-options-bot/.env && chmod 600 ~/alpaca-options-bot/.env
```

## Part 7. First run (10 minutes)

1. Check the plumbing without the model, then with it:

   ```bash
   cd ~/alpaca-options-bot && python3 trader.py selftest
   ```

   ```bash
   cd ~/alpaca-options-bot && python3 trader.py check
   ```

2. Let him write. The first run takes a minute or two while the model loads:

   ```bash
   cd ~/alpaca-options-bot && python3 trader.py diary
   ```

3. Talk to him:

   ```bash
   cd ~/alpaca-options-bot && python3 trader.py chat
   ```

4. Run the whole daily job once by hand. It should end with "Saved to GitHub":

   ```bash
   ~/alpaca-options-bot/mac_mini/nightly.sh
   ```

## Part 8. Put it on a schedule (2 minutes)

```bash
~/alpaca-options-bot/mac_mini/install_schedule.sh
```

It now runs at 6:00 pm on weekdays and 6:30 am Tuesday to Saturday, in the
Mac mini's own time zone. Its log is `~/alpaca-options-bot/mac_mini/nightly.log`.

---

## What you get

| File | What it is |
|---|---|
| `memory/DIARY.md` | His daily diary, in character |
| `memory/shadow_picks.csv` | The trades he would make. Never placed. |
| `memory/TRADER_NOTES.md` | Notes he writes to himself each Friday and reads back before every entry |
| `memory/REVIEW.md` | Now also scores his picks against the rules' own top picks |
| `memory/last_facts.txt` | The exact facts he was given for his latest output, so you can check him |

## Shaping his personality

Edit `memory/PERSONA.md` in any text editor. The next entry uses the new
version. To try a change straight away: `python3 trader.py diary`.

## Guard rails

- **He cannot trade or change a rule.** His script never contacts the broker.
- **He cannot invent numbers.** Every dollar amount and percentage he writes
  is checked against the bot's records. He gets one chance to rewrite; if a
  made-up figure survives, the entry is saved with a warning naming it.
- **His picks must come from the day's real signals.** Anything else is dropped.
- **Headlines are background only.** They are passed to him as data, and
  since he has no ability to act, a misleading headline can at worst produce
  a silly diary entry.

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Could not reach Ollama" | `brew services start ollama`, wait 10 seconds, try again |
| "Model ... is NOT downloaded" | Run the `ollama pull` line it prints, or fix `MODEL=` in `mac_mini/config.env` |
| Very slow, or the Mac freezes | The model is too big for the memory. Pick the next size down in Part 1. |
| He rambles or breaks character | Use a larger model, or tighten `memory/PERSONA.md` |
| "Nothing new to save" every day | Normal on weekends and holidays. Otherwise read `mac_mini/nightly.log`. |
| The schedule did not run | The Mac was asleep or off. Check Part 2, then run `mac_mini/nightly.sh` by hand. |

## Later, if you want more

- **A bigger model** is the single biggest improvement, and it is one line in
  `mac_mini/config.env`.
- **Reach it from anywhere:** a free Tailscale account on both Macs lets you
  use Screen Sharing and `ssh` away from home.
- **Work on it with Claude:** install the Claude desktop app on the Mac mini
  and open the `alpaca-options-bot` folder there.
- **Give him a real say:** only after his shadow picks have beaten the rules'
  picks over a few weeks, and only by letting him choose among signals the
  rules already approve. That would be a deliberate, logged change.
