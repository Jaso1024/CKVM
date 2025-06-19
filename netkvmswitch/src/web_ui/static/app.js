document.addEventListener('DOMContentLoaded', () => {
    const clientList = document.getElementById('client-list');
    const videoGrid = document.getElementById('video-grid');
    const inputForwardingCheckbox = document.getElementById('input-forwarding');
    const startAgentBtn = document.getElementById('start-agent-btn');
    const stopAgentBtn = document.getElementById('stop-agent-btn');
    const refreshIntervalSelect = document.getElementById('refresh-interval');
    const refreshModal = document.getElementById('refresh-modal');
    const refreshYesBtn = document.getElementById('refresh-yes');
    const refreshNoBtn = document.getElementById('refresh-no');
    const shutdownHubBtn = document.getElementById('shutdown-hub-btn');
    const hubIpInput = document.getElementById('hub-ip');
    const networkAccessibleCheckbox = document.getElementById('network-accessible');

    let players = {};
    let activeIOClient = null;
    let refreshTimer = null;

    function destroyAllPlayers() {
        for (const addr in players) {
            if (players[addr].jmuxer) players[addr].jmuxer.destroy();
            if (players[addr].wrapper) players[addr].wrapper.remove();
        }
        players = {};
    }

    function connectWebSocket() {
        destroyAllPlayers();
        fetchClients();

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/video`;
        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => console.log('Video WebSocket connected');
        ws.onmessage = (event) => {
            const data = new Uint8Array(event.data);
            const addrBytes = data.slice(0, 40);
            const h264Data = data.slice(40);
            const decoder = new TextDecoder();
            const address = decoder.decode(addrBytes).trim();

            if (players[address] && players[address].jmuxer) {
                players[address].jmuxer.feed({ video: h264Data });
                players[address].frameCount++;
            }
        };
        ws.onclose = () => {
            console.log('Video WebSocket disconnected. Reconnecting in 2 seconds...');
            setTimeout(connectWebSocket, 2000);
        };
        ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            ws.close();
        };
    }

    async function fetchClients() {
        try {
            const response = await fetch('/api/clients');
            const data = await response.json();
            updateClientList(data.clients);
            updateVideoGrid(data.clients);
        } catch (error) {
            console.error('Error fetching clients:', error);
        }
    }

    function updateVideoGrid(clients) {
        const currentAddresses = Object.keys(players);
        const newAddresses = Object.keys(clients);

        currentAddresses.forEach(addr => {
            if (!newAddresses.includes(addr)) {
                if (players[addr]) {
                    players[addr].wrapper.remove();
                    if (players[addr].jmuxer) players[addr].jmuxer.destroy();
                    delete players[addr];
                }
            }
        });

        newAddresses.forEach(addr => {
            if (!currentAddresses.includes(addr)) {
                const client = clients[addr];
                const wrapper = document.createElement('div');
                wrapper.className = 'video-wrapper';
                wrapper.dataset.address = addr;

                const video = document.createElement('video');
                video.autoplay = true;
                video.muted = true;
                video.playsInline = true;

                const fpsDisplay = document.createElement('div');
                fpsDisplay.className = 'fps-display';
                fpsDisplay.textContent = 'FPS: 0';

                wrapper.appendChild(video);
                wrapper.appendChild(fpsDisplay);
                videoGrid.appendChild(wrapper);

                const jmuxer = new JMuxer({
                    node: video,
                    mode: 'video',
                    flushingTime: 0,
                    fps: 60,
                    debug: false,
                });

                players[addr] = {
                    jmuxer: jmuxer,
                    wrapper: wrapper,
                    video: video,
                    fpsDisplay: fpsDisplay,
                    frameCount: 0,
                };

                wrapper.addEventListener('mouseenter', () => handleMouseEnter(addr));
                wrapper.addEventListener('mouseleave', () => handleMouseLeave(addr));
                wrapper.addEventListener('mousemove', (e) => handleMouseMove(e, addr));
            }
        });
    }
    
    setInterval(() => {
        for (const addr in players) {
            if (players[addr].fpsDisplay) {
                players[addr].fpsDisplay.textContent = `FPS: ${players[addr].frameCount}`;
                players[addr].frameCount = 0;
            }
        }
    }, 1000);

    function handleMouseEnter(address) {
        activeIOClient = address;
        document.querySelectorAll('.video-wrapper').forEach(w => {
            w.classList.toggle('active', w.dataset.address === address);
            w.classList.toggle('inactive', w.dataset.address !== address);
        });
    }

    function handleMouseLeave(address) {
        if (activeIOClient === address) activeIOClient = null;
        document.querySelectorAll('.video-wrapper').forEach(w => w.classList.remove('active', 'inactive'));
    }

    function handleMouseMove(event, address) {
        if (activeIOClient !== address || !inputForwardingCheckbox.checked) return;
        const rect = event.target.getBoundingClientRect();
        const normalizedX = (event.clientX - rect.left) / rect.width;
        const normalizedY = (event.clientY - rect.top) / rect.height;
        sendIOEvent(address, 'mouse_event', { event_type: 'move', x: normalizedX, y: normalizedY });
    }

    function handleMouseClick(event) {
        if (!activeIOClient || !inputForwardingCheckbox.checked) return;
        const rect = players[activeIOClient].video.getBoundingClientRect();
        const normalizedX = (event.clientX - rect.left) / rect.width;
        const normalizedY = (event.clientY - rect.top) / rect.height;
        const payload = {
            event_type: 'click',
            x: normalizedX,
            y: normalizedY,
            button: `Button.${event.button === 0 ? 'left' : 'right'}`,
            pressed: event.type === 'mousedown',
        };
        sendIOEvent(activeIOClient, 'mouse_event', payload);
    }

    function handleMouseScroll(event) {
        if (!activeIOClient || !inputForwardingCheckbox.checked) return;
        event.preventDefault();
        sendIOEvent(activeIOClient, 'mouse_event', { event_type: 'scroll', dx: event.deltaX, dy: event.deltaY });
    }

    function handleKeyEvent(event) {
        if (!activeIOClient || !inputForwardingCheckbox.checked) return;
        event.preventDefault();
        sendIOEvent(activeIOClient, 'key_event', { event_type: event.type, key: event.key });
    }

    async function sendIOEvent(address, event_type, payload) {
        try {
            await fetch('/api/io/event', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address, event_type, payload }),
            });
        } catch (error) {
            console.error(`Error sending I/O event:`, error);
        }
    }

    function updateClientList(clients) {
        clientList.innerHTML = '';
        for (const address in clients) {
            const client = clients[address];
            const li = document.createElement('li');
            li.textContent = `${client.name} (${address})`;
            li.dataset.address = address;
            if (client.is_active) li.classList.add('active');
            li.addEventListener('click', () => setActiveClient(address));
            clientList.appendChild(li);
        }
    }

    async function setActiveClient(address) {
        try {
            await fetch('/api/clients/active', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ address: address }),
            });
            fetchClients();
        } catch (error) {
            console.error('Error setting active client:', error);
        }
    }

    async function setInputForwarding(enabled) {
        try {
            await fetch('/api/hub/set_input_forwarding', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled }),
            });
        } catch (error) {
            console.error('Error setting input forwarding:', error);
        }
    }

    async function startAgent() {
        try {
            await fetch('/api/agent/start', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hub_ip: hubIpInput.value })
            });
            updateAgentButtons(true);
        } catch (error) {
            console.error('Error starting agent:', error);
        }
    }

    async function stopAgent() {
        try {
            await fetch('/api/agent/stop', { method: 'POST' });
            updateAgentButtons(false);
        } catch (error) {
            console.error('Error stopping agent:', error);
        }
    }

    function updateAgentButtons(isRunning) {
        startAgentBtn.style.display = isRunning ? 'none' : 'block';
        stopAgentBtn.style.display = isRunning ? 'block' : 'none';
    }

    function setupRefreshTimer() {
        if (refreshTimer) clearTimeout(refreshTimer);
        const interval = parseInt(refreshIntervalSelect.value, 10);
        if (interval > 0) {
            refreshTimer = setTimeout(() => showRefreshModal(interval), interval);
        }
    }

    function showRefreshModal(interval) {
        refreshModal.style.display = 'flex';
        refreshYesBtn.onclick = () => {
            refreshModal.style.display = 'none';
            connectWebSocket();
            setupRefreshTimer();
        };
        refreshNoBtn.onclick = () => {
            refreshModal.style.display = 'none';
            if (refreshTimer) clearTimeout(refreshTimer);
            refreshTimer = setTimeout(() => showRefreshModal(interval), interval * 10);
        };
    }

    async function setNetworkAccessible(enabled) {
        try {
            await fetch('/api/hub/set_network_accessible', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: enabled }),
            });
        } catch (error) {
            console.error('Error setting network accessible:', error);
        }
    }

    document.addEventListener('mousedown', handleMouseClick);
    document.addEventListener('mouseup', handleMouseClick);
    document.addEventListener('wheel', handleMouseScroll, { passive: false });
    document.addEventListener('keydown', handleKeyEvent);
    document.addEventListener('keyup', handleKeyEvent);

    inputForwardingCheckbox.addEventListener('change', (event) => setInputForwarding(event.target.checked));
    startAgentBtn.addEventListener('click', startAgent);
    stopAgentBtn.addEventListener('click', stopAgent);
    refreshIntervalSelect.addEventListener('change', setupRefreshTimer);
    shutdownHubBtn.addEventListener('click', async () => {
        if (confirm('Are you sure you want to shut down the entire hub?')) {
            try {
                await fetch('/api/hub/shutdown', { method: 'POST' });
                document.body.innerHTML = '<h1>Hub has been shut down.</h1>';
            } catch (error) {
                console.error('Error shutting down hub:', error);
            }
        }
    });
    networkAccessibleCheckbox.addEventListener('change', (event) => {
        setNetworkAccessible(event.target.checked);
    });

    connectWebSocket();
    fetchClients();
    setInterval(fetchClients, 2000);
    setupRefreshTimer();
});
