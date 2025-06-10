# NetKVMSwitch Quick Start Guide

This guide will help you quickly test NetKVMSwitch on a single laptop where both the server and client run on the same machine.

## Prerequisites

1. **Python 3.8+** installed
2. **Dependencies** installed: `pip install -r requirements.txt`
3. **Certificates** generated: `python generate_certs.py`

## Single-Machine Testing Setup

### Option 1: Automatic Setup (Recommended)

**Step 1: Start the UI (which auto-starts the server)**
```bash
cd netkvmswitch
python run_ui.py
```

**Step 2: Open the UI**
- Go to: http://localhost:8501
- Click "Start Server" in the sidebar (if not auto-started)
- Click "Connect to Server"

**Step 3: Start a client agent**
```bash
cd netkvmswitch
python run_client.py
```

### Option 2: Manual Setup

**Step 1: Start the server**
```bash
cd netkvmswitch
python run_server.py
```

**Step 2: Start the UI**
```bash
cd netkvmswitch
python run_ui.py
```

**Step 3: Start a client agent**
```bash
cd netkvmswitch
python run_client.py
```

## Testing the KVM Functionality

1. **Video Feed**: You should see your desktop being streamed in the UI
2. **Input Control**: 
   - Select the client in the UI sidebar
   - Your keyboard/mouse input should now control the "client" machine (same machine in this test)
   - **Note**: Input might feel recursive since you're controlling the same machine you're viewing from

## Configuration for Testing

The default configuration (`config.json`) is optimized for testing:

- **Video Quality**: 60% (good balance of quality/performance)
- **Video Width**: 1024px (reasonable size for testing)
- **FPS**: 25 (smooth but not resource-intensive)
- **TLS**: Enabled (production-ready security)

## Testing Multiple Clients

To simulate multiple clients on one machine:

**Terminal 1: Client 1**
```bash
cd netkvmswitch
NETKVM_CLIENT_NAME="Desktop-1" python run_client.py
```

**Terminal 2: Client 2** 
```bash
cd netkvmswitch
NETKVM_CLIENT_NAME="Desktop-2" python run_client.py
```

## Environment Variables for Testing

You can override configuration with environment variables:

```bash
# Disable TLS for testing (faster)
export NETKVM_USE_TLS=false

# Change client name
export NETKVM_CLIENT_NAME="TestClient"

# Change video quality
export NETKVM_VIDEO_QUALITY=80

# Change server host for remote testing
export NETKVM_CLIENT_SERVER_HOST=192.168.1.100
```

## Commands Summary

| Component | Command | Purpose |
|-----------|---------|---------|
| **UI** | `python run_ui.py` | Web interface at http://localhost:8501 |
| **Server** | `python run_server.py` | Central hub server |
| **Client** | `python run_client.py` | Source agent (screen sharing) |
| **Certs** | `python generate_certs.py` | Generate TLS certificates |

## Ports Used

| Port | Purpose | Protocol |
|------|---------|----------|
| **8501** | Streamlit UI | HTTP |
| **12345** | Client connections | TCP/TLS |
| **12346** | Video streaming | UDP |
| **12347** | UI video feed | UDP |
| **12348** | UI control commands | TCP |

## Troubleshooting

### "Certificate not found" error
```bash
cd netkvmswitch
python generate_certs.py
```

### "Port already in use" error
- Stop any running instances
- Wait 10 seconds for ports to be released
- Try again

### "Permission denied" on input capture
- On Linux/Mac: Run with `sudo` or configure input permissions
- On Windows: Run as Administrator

### Video feed not showing
- Check if client is connected (look for connection message)
- Verify client is selected as "Active" in UI
- Check firewall/antivirus blocking UDP traffic

### Client can't connect to server
- Ensure server is running first
- Check firewall settings
- For remote connections, update `NETKVM_CLIENT_SERVER_HOST`

## Performance Tips

For better performance during testing:

1. **Reduce video quality**: Set `NETKVM_VIDEO_QUALITY=30`
2. **Lower resolution**: Set video_width to 640 in config.json
3. **Reduce FPS**: Set fps to 15 in config.json
4. **Disable TLS**: Set `NETKVM_USE_TLS=false` (testing only)

## Next Steps

Once basic testing works:

1. **Remote Testing**: Run client on a different machine
2. **Multiple Clients**: Connect several machines
3. **Production Setup**: Configure proper hostnames and certificates
4. **Advanced Features**: Test clipboard sharing, file transfer (when implemented)

---

🎉 **Success**: If you can see your screen in the UI and switch between clients, NetKVMSwitch is working correctly! 