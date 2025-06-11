document.addEventListener('DOMContentLoaded', () => {
    const clientList = document.getElementById('client-list');
    const playerNode = document.getElementById('player');
    const inputForwardingCheckbox = document.getElementById('input-forwarding');
    const startAgentBtn = document.getElementById('start-agent-btn');
    const stopAgentBtn = document.getElementById('stop-agent-btn');
    const fpsDisplay = document.getElementById('fps-display');

    let jmuxer = null;
    let frameCount = 0;

    // FPS calculation
    setInterval(() => {
        fpsDisplay.textContent = `FPS: ${frameCount}`;
        frameCount = 0;
    }, 1000);

    function initJmuxer() {
        if (jmuxer) {
            jmuxer.destroy();
        }
        jmuxer = new JMuxer({
            node: 'player',
            mode: 'video',
            flushingTime: 0,
            fps: 60,
            debug: false
        });
    }

    function connectWebSocket() {
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${window.location.host}/ws/video`;
        const ws = new WebSocket(wsUrl);
        ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
            console.log('Video WebSocket connected');
        };

        ws.onmessage = (event) => {
            if (jmuxer) {
                jmuxer.feed({
                    video: new Uint8Array(event.data)
                });
                frameCount++;
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
        } catch (error) {
            console.error('Error fetching clients:', error);
        }
    }

    function updateClientList(clients) {
        clientList.innerHTML = '';
        for (const address in clients) {
            const client = clients[address];
            const li = document.createElement('li');
            li.textContent = `${client.name} (${address})`;
            li.dataset.address = address;
            if (client.is_active) {
                li.classList.add('active');
            }
            li.addEventListener('click', () => {
                setActiveClient(address);
            });
            clientList.appendChild(li);
        }
    }

    async function setActiveClient(address) {
        try {
            await fetch('/api/clients/active', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ address: address }),
            });
            fetchClients(); // Refresh the list to show the new active client
        } catch (error) {
            console.error('Error setting active client:', error);
        }
    }

    async function setInputForwarding(enabled) {
        try {
            await fetch('/api/hub/set_input_forwarding', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ enabled: enabled }),
            });
        } catch (error) {
            console.error('Error setting input forwarding:', error);
        }
    }

    async function startAgent() {
        try {
            await fetch('/api/agent/start', { method: 'POST' });
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

    // Event Listeners
    inputForwardingCheckbox.addEventListener('change', (event) => {
        setInputForwarding(event.target.checked);
    });

    startAgentBtn.addEventListener('click', startAgent);
    stopAgentBtn.addEventListener('click', stopAgent);

    // Initial setup
    initJmuxer();
    connectWebSocket();
    fetchClients();
    setInterval(fetchClients, 5000); // Refresh client list every 5 seconds
});
