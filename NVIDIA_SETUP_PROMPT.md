# NVIDIA GPU Setup for Docker & Ollama — Gemini CLI Guide

You are assisting a user who needs to enable NVIDIA GPU acceleration for Docker containers and Ollama on a Pop!_OS 24.04 LTS laptop with an RTX 5060 GPU (8GB VRAM, driver 580.126.18, CUDA 13.0).

## Context

- **Current state:** Host Ollama (systemd service on port 11434) is CPU-only. Docker GPU passthrough is not configured.
- **Goal:** Install NVIDIA Container Toolkit and enable GPU for the Docker Ollama service so WintripAI Fase 3 chat becomes faster.
- **Architecture:** The updated docker-compose.yml now uses the Docker Ollama service (with GPU) instead of the host Ollama.
- **No destructive changes:** Docker volumes and Ollama models are preserved.

---

## Step 1: Verify Prerequisites

**Action:** Ask the user to run:

```bash
uname -a
cat /etc/os-release | grep -E '^(ID|VERSION_ID|PRETTY_NAME)='
nvidia-smi
sudo whoami
```

**What to expect:**
- OS: Pop!_OS 24.04 LTS
- GPU: NVIDIA GeForce RTX 5060 (8GB VRAM)
- Driver: 580.126.18
- CUDA: 13.0
- `sudo whoami` should return `root` (confirming sudo is available)

**If something is wrong:** Stop and have the user verify their environment matches the requirements above.

---

## Step 2: Update Package Lists

**Explanation:** This refreshes the package manager's cache so we can install the latest NVIDIA Container Toolkit.

**Action:** Ask the user to run:

```bash
sudo apt-get update
```

**Expected output:** Lines about "Hit" or "Get" for various package sources, ending with "Reading package lists... Done."

**If it fails:** Check internet connection or apt state. User may need to run `sudo apt-get clean` first.

---

## Step 3: Install Prerequisites

**Explanation:** We need `curl` (to download NVIDIA's GPG key) and `gnupg2` (to verify the key).

**Action:** Ask the user to run:

```bash
sudo apt-get install -y curl gnupg2
```

**Expected output:** "Reading package lists... Done" and package installation messages. Should complete quickly if already installed.

---

## Step 4: Add NVIDIA Repository — GPG Key

**Explanation:** This downloads NVIDIA's GPG public key and stores it on the system. We use it later to verify the authenticity of the NVIDIA Container Toolkit packages.

**Action:** Ask the user to run:

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
```

**Expected output:** No output (silent on success). The file `/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg` should now exist.

**Verification:** Ask user to run:
```bash
ls -lh /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
```
Should show a file ~5-10 KB in size.

**If it fails:** Likely network issue. Confirm user has internet, then retry.

---

## Step 5: Add NVIDIA Repository — Apt Source List

**Explanation:** This adds the official NVIDIA repository to apt so we can install and update the Container Toolkit package.

**Action:** Ask the user to run:

```bash
echo 'deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/ubuntu22.04 amd64 https://nvidia.github.io/libnvidia-container' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
```

**Expected output:** The echo'ed line (same as what was piped in).

**Verification:** Ask user to run:
```bash
cat /etc/apt/sources.list.d/nvidia-container-toolkit.list
```
Should show the deb line with the signed-by path.

---

## Step 6: Update Package Lists Again

**Explanation:** Now that we've added the NVIDIA repository, we need to refresh apt's cache so it knows about packages from that repo.

**Action:** Ask the user to run:

```bash
sudo apt-get update
```

**Expected output:** Lines about "Hit", "Get", etc., including the nvidia.github.io repository. Should end with "Reading package lists... Done."

**If there are GPG errors:** This is unexpected; the GPG key may not have been added correctly. Have user re-verify Step 4.

---

## Step 7: Install NVIDIA Container Toolkit

**Explanation:** This is the main package that provides GPU support to Docker. It includes `nvidia-container-cli` and the required runtime hooks.

**Action:** Ask the user to run:

```bash
sudo apt-get install -y nvidia-container-toolkit
```

**Expected output:** Package download and installation. Should complete without errors. Look for "Setting up nvidia-container-toolkit" in the output.

**Verification:** Ask user to run:
```bash
nvidia-container-cli --version
```
Should return a version number (e.g., `v1.15.0`).

**If it fails:** Likely apt/network issue. Ask user to check the error message and retry.

---

## Step 8: Configure Docker Runtime

**Explanation:** This command tells Docker to use the NVIDIA Container Runtime when the `--gpus` flag is used. It modifies Docker's daemon configuration to register the NVIDIA runtime.

**Action:** Ask the user to run:

```bash
sudo nvidia-ctk runtime configure --runtime=docker
```

**Expected output:** Should be quiet. No errors means success.

**Verification:** Ask user to run:
```bash
docker info --format '{{json .Runtimes}}' | jq .
```
Should show `nvidia` as one of the available runtimes (e.g., `{"io.containerd.runc.v2": {...}, "nvidia": {...}, ...}`).

**If nvidia runtime is missing:** The configuration may not have applied. Ask user to retry this step or check `/etc/docker/daemon.json` exists and contains the nvidia runtime config.

---

## Step 9: Restart Docker Daemon

**Explanation:** Docker reads its configuration on startup. We need to restart it so it picks up the new NVIDIA runtime configuration.

**Action:** Ask the user to run:

```bash
sudo systemctl restart docker
```

**Expected output:** No output. Command should return silently.

**Verification (wait 5 seconds, then):** Ask user to run:
```bash
docker ps
```
Should return `CONTAINER ID   IMAGE   COMMAND   CREATED   STATUS   PORTS   NAMES` (an empty list is fine).

**If Docker doesn't respond:** Wait 10 more seconds and retry. If still failing, ask user to run `sudo systemctl status docker` to see the error.

---

## Step 10: Test Docker GPU Passthrough

**Explanation:** This is the critical test. We're running NVIDIA's CUDA container to confirm Docker can pass the GPU to containers.

**Action:** Ask the user to run:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

**Expected output:** The `nvidia-smi` output showing the RTX 5060 GPU with 0% utilization and 2 MB used. This proves GPU passthrough works.

Example:
```
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 580.126.18             Driver Version: 580.126.18     CUDA Version: 13.0     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|   0  NVIDIA GeForce RTX 5060 ...    Off |   00000000:01:00.0 Off |                  N/A |
| N/A   54C    P8              4W /   80W |       2MiB /   8151MiB |      0%      Default |
+-----------------------------------------------------------------------------------------+
```

**If this fails with "failed to discover GPU vendor from CDI":** The NVIDIA runtime was not properly configured. Go back to Step 8 and Step 9. Verify the nvidia runtime is in `docker info`.

**If Docker container downloads and then times out:** Network issue pulling the image. Retry after 30 seconds.

---

## Step 11: Restart WintripAI Fase 3 with GPU-Enabled Ollama

**Explanation:** The docker-compose.yml has been updated to use the Docker Ollama service with GPU support. We'll restart the services to apply these changes.

**Action:** Ask the user to run:

```bash
cd /home/pwintri2/WintripAI
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 down
```

**Expected output:** Stops and removes the old containers. Output will show container removal messages.

**Then:**

```bash
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 up -d --build
```

**Expected output:** Builds the Ouroboros image and starts both ouroboros and ollama containers. May take 1–2 minutes.

**Verification (wait 30 seconds for services to be ready, then):** Ask user to run:

```bash
docker ps -f "label=com.docker.compose.project=ouroboros-fase2"
```

Should list two containers: `ouroboros-fase2-ouroboros-1` and `ouroboros-fase2-ollama-1`, both with status `Up`.

---

## Step 12: Verify GPU Inside Docker Ollama

**Explanation:** We check inside the Ollama container to confirm the GPU is available.

**Action:** Ask the user to run:

```bash
docker exec -it ouroboros-fase2-ollama-1 nvidia-smi
```

**Expected output:** Same `nvidia-smi` output as Step 10, confirming the GPU is visible inside the container.

**If it says "command not found":** The NVIDIA CUDA toolkit is not installed in the container. This is expected for the base Ollama image. The GPU is still available to Ollama's CUDA library; we just can't run `nvidia-smi` to verify it directly. **This is OK — Ollama will use the GPU automatically.**

---

## Step 13: Check Ollama GPU Usage

**Explanation:** We'll load a model on Ollama and watch it use GPU. The best way is to trigger a request and check `nvidia-smi` from the host.

**Action:** Ask the user to open two terminal windows side-by-side:

**Terminal 1 (GPU monitor):**
```bash
watch -n 0.5 'nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader,nounits'
```
This will refresh every 0.5 seconds showing GPU utilization and memory usage.

**Terminal 2 (trigger a request):**
```bash
curl -fsS http://127.0.0.1:11435/api/chat -d '{
  "model":"llama3.2:latest",
  "stream":false,
  "messages":[{"role":"user","content":"Reply in one sentence: are you available?"}],
  "options":{"num_predict":40,"num_ctx":1024}
}' | head -c 200
```

**Expected output in Terminal 1:** When the curl request is running, you should see GPU utilization spike above 0% and memory usage increase (e.g., `60 5120` means 60% GPU util, 5120 MB used). After the request completes, it should drop back to low values.

**What if GPU utilization stays at 0%?** The model may not be loaded yet, or Ollama defaults to CPU. Run the curl command again to trigger a real inference after the model is loaded.

---

## Step 14: Test WintripAI Fase 3 Health & Chat

**Explanation:** Now we verify that Fase 3 is working and can talk to the GPU-enabled Docker Ollama.

**Action:** Ask the user to run:

```bash
curl -fsS http://127.0.0.1:7860/health
```

**Expected output:** A JSON response indicating the service is healthy, e.g.:
```json
{"status":"ok"}
```

**Then test chat:**

```bash
curl -fsS http://127.0.0.1:7860/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Who are you? One sentence."}'
```

**Expected output:** A JSON response with a chat completion from Ollama. Should NOT contain error messages like "Ollama is nu niet tijdig beschikbaar" (Ollama not available in time).

**If you get an error:** Check `docker logs ouroboros-fase2-ouroboros-1` to see what went wrong. Common issues:
- Ollama service not ready yet (wait 30 more seconds and retry)
- Model not found (Ollama will auto-pull it; this takes 1–5 minutes depending on model size)
- Network issue between Ouroboros and Ollama (check they're on the same Docker network)

---

## Step 15: Benchmark (Optional)

**Explanation:** Compare response speed before/after GPU enablement.

**Action:** Ask the user to run the following and note the time:

```bash
time curl -fsS http://127.0.0.1:7860/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Write exactly: GPU acceleration is working."}' > /tmp/response.json

cat /tmp/response.json | jq .
```

**Expected output:** The `time` command will show `real`, `user`, `sys` times. The response should come back in seconds (not minutes like CPU-only would).

---

## Troubleshooting Checklist

If something goes wrong, have the user check:

1. **NVIDIA runtime not available after Step 8:**
   - Manually verify: `cat /etc/docker/daemon.json | grep nvidia`
   - Restart Docker again: `sudo systemctl restart docker`

2. **GPU passthrough test (Step 10) fails:**
   - Is the GPU visible on the host? `nvidia-smi`
   - Are you using `--gpus all` flag?
   - Retry after restarting Docker: `sudo systemctl restart docker`

3. **Ollama container doesn't start:**
   - Check logs: `docker logs ouroboros-fase2-ollama-1`
   - Confirm GPU is available: `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi`

4. **GPU not showing in Ollama:**
   - This may be expected if Ollama auto-selects CPU. Trigger inference and watch `nvidia-smi` on the host.
   - If GPU stays idle, check Ollama logs: `docker logs ouroboros-fase2-ollama-1`

5. **Chat is still slow:**
   - Models may still be loading. Wait 5 minutes and try again.
   - Check if the model was actually pulled: `docker exec -it ouroboros-fase2-ollama-1 ollama list`

---

## Success Criteria

All of the following should be true:

- ✅ `nvidia-smi` shows the RTX 5060 on the host
- ✅ `docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi` succeeds
- ✅ `docker ps` shows both ouroboros and ollama containers running
- ✅ `curl http://127.0.0.1:7860/health` returns OK
- ✅ Chat responses complete in < 10 seconds (GPU-assisted)
- ✅ `nvidia-smi` shows memory usage spike when running a chat request
- ✅ No "Ollama not available" errors in Fase 3 responses

---

## Summary for the User

After these steps:

1. **Docker GPU support is enabled** — Any Docker container can now use `--gpus all` to access the RTX 5060.
2. **Ollama is now in Docker with GPU** — The compose file uses the Docker Ollama service (port 11435 mapped to 11434 inside) with GPU access.
3. **WintripAI Fase 3 talks to Docker Ollama** — Via the compose network (`OLLAMA_BASE_URL=http://ollama:11434`).
4. **GPU acceleration is active** — Chat responses should be materially faster than before.
5. **Host Ollama (systemd) remains unchanged** — Still CPU-only, but unused by Fase 3.

**Optional follow-up:** If the user wants to also enable GPU on the host Ollama (for direct use), that would require fixing the missing `libggml-base.so.0` library, which is out of scope for this setup.
