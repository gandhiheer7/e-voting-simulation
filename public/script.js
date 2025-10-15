const API_BASE = ''; // Vercel automatically routes /api

// --- DOM Element References ---
const logPanel = document.getElementById('log-panel');
const candidateList = document.getElementById('candidate-list');
const statusContainer = document.getElementById('status-container');
const candidateNameInput = document.getElementById('candidate-name');
const voterIdInput = document.getElementById('voter-id');

// --- Log & State Update Functions ---
function appendLog(logArray) {
    if (!logArray) return;
    logArray.forEach(line => {
        const p = document.createElement('p');
        p.textContent = `> ${line}`;
        p.className = 'log-line text-green-400';
        if (line.includes('!!') || line.includes('down')) {
            p.className = 'log-line text-red-400 font-bold';
        } else if (line.includes('LEADER')) {
             p.className = 'log-line text-yellow-400';
        }
        logPanel.appendChild(p);
    });
    logPanel.scrollTop = logPanel.scrollHeight;
}

function updateUI(state) {
    if (!state) return;
    
    // Update candidate list for voters
    candidateList.innerHTML = '';
    if (Object.keys(state.candidates || {}).length > 0) {
         for (const name in state.candidates) {
            const button = document.createElement('button');
            button.className = "w-full btn-primary text-white font-medium rounded-lg px-5 py-3 text-center";
            button.textContent = `Vote for ${name}`;
            button.onclick = () => castVote(name);
            candidateList.appendChild(button);
        }
    } else {
         candidateList.innerHTML = '<p class="text-gray-500">Admin needs to add candidates.</p>';
    }

    // Update status panel
    statusContainer.innerHTML = '';
    for (const [nodeId, nodeInfo] of Object.entries(state.nodes)) {
        const statusDiv = document.createElement('div');
        const statusColor = nodeInfo.status === 'UP' ? 'text-green-500' : 'text-red-500';
        const leaderText = nodeInfo.is_leader ? '👑 LEADER' : '';
        
        const votes = Object.entries(nodeInfo.votes).map(([c, v]) => `${c}: ${v}`).join(', ');

        statusDiv.innerHTML = `
            <div class="flex justify-between items-center">
               <div class="font-bold">${nodeId} <span class="${statusColor}">${nodeInfo.status}</span> <span class="text-yellow-400">${leaderText}</span></div>
               <button onclick="failNode('${nodeId}')" class="btn-danger text-white text-xs font-bold py-1 px-2 rounded">Simulate Failure</button>
            </div>
            <div class="text-sm text-gray-400 pl-2">Votes: { ${votes} }</div>
        `;
        statusContainer.appendChild(statusDiv);
    }
}

// --- API Call Functions ---
async function apiCall(endpoint, method = 'GET', body = null) {
    logPanel.innerHTML += `<p class="log-line text-gray-500">> Firing request to ${endpoint}...</p>`;
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' },
        };
        if (body) options.body = JSON.stringify(body);

        const response = await fetch(`${API_BASE}${endpoint}`, options);
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        appendLog(data.log);
        updateUI(data.state || await (await fetch(`${API_BASE}/api/get-state`)).json());
    } catch (error) {
        appendLog([`API Error: ${error.message}`]);
    }
}

function initializeSystem() {
    logPanel.innerHTML = '';
    apiCall('/api/initialize', 'POST');
}

function addCandidate() {
    const name = candidateNameInput.value;
    if (name) {
        apiCall('/api/add-candidate', 'POST', { name });
        candidateNameInput.value = '';
    }
}

function castVote(candidateName) {
    const voterId = voterIdInput.value;
    if (!voterId) {
        alert('Please enter a Voter ID.');
        return;
    }
    apiCall('/api/vote', 'POST', { voterId, candidateName });
}

function failNode(node_id) {
    apiCall('/api/fail-node', 'POST', { node_id });
}

// --- Initial Load ---
window.onload = () => {
     initializeSystem();
     setInterval(() => {
        // Periodically sync state in case others are using it
        apiCall('/api/get-state');
     }, 15000); // Sync every 15 seconds
};