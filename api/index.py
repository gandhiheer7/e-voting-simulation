import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import redis
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

# Initialize Flask App and enable Cross-Origin Resource Sharing (CORS)
app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
NUM_NODES = 3 # The total number of nodes we are simulating

# --- REDIS CONNECTION ---
# Connect to the Redis database provided by Vercel KV
redis_client = None
if os.getenv("REDIS_URL"):
    try:
        redis_client = redis.from_url(os.getenv("REDIS_URL"))
    except Exception as e:
        print(f"Error: Could not connect to Redis. {e}")
else:
    print("Error: REDIS_URL environment variable not set.")

# --- HELPER FUNCTIONS ---

def get_system_state():
    """Fetches the entire system state from Redis."""
    if not redis_client: return None
    state_str = redis_client.get('system_state')
    return json.loads(state_str) if state_str else None

def save_system_state(state):
    """Saves the entire system state back to Redis."""
    if not redis_client: return
    redis_client.set('system_state', json.dumps(state))

def get_leader(nodes):
    """Finds the current leader among the active ('UP') nodes."""
    for node_id, node_info in nodes.items():
        if node_info.get('is_leader') and node_info.get('status') == 'UP':
            return node_id, node_info
    return None, None

def run_leader_election(nodes, log):
    """
    DEMONSTRATES: Experiment 4 - Leader Election (Bully/Ring Algorithm Simulation)
    Simulates a leader election. Elects the active ('UP') node with the highest ID.
    """
    log.append("LEADER ELECTION: Starting leader election simulation.")
    potential_leader_id = -1
    new_leader_node_id = None
    
    for node_id_str, node_info in nodes.items():
        if node_info.get('status') == 'UP':
            node_num = int(node_id_str.split('-')[1])
            if node_num > potential_leader_id:
                potential_leader_id = node_num
                new_leader_node_id = node_id_str
    
    if new_leader_node_id:
        for node_id in nodes:
            nodes[node_id]['is_leader'] = (node_id == new_leader_node_id)
        log.append(f"LEADER ELECTION: {new_leader_node_id} is the new leader.")
    else:
        log.append("LEADER ELECTION: No available nodes to elect as leader.")
    
    return nodes

# --- API ROUTES ---

@app.route('/api/initialize', methods=['POST'])
def initialize_system():
    """Initializes or resets the system to a default state."""
    log = ["[INIT] Initializing system..."]
    
    initial_state = {
        "nodes": {},
        "candidates": {},
        "voted_ids": [],
        "global_lamport_clock": 0,
        "request_counter": 0
    }
    
    for i in range(1, NUM_NODES + 1):
        node_id = f'node-{i}'
        initial_state["nodes"][node_id] = {
            "status": "UP",
            "is_leader": (i == 1), # Node 1 starts as the leader
            "votes": {}
        }
        
    save_system_state(initial_state)
    log.append(f"[INIT] System reset complete. {NUM_NODES} nodes created. Node-1 is leader.")
    
    return jsonify({"log": log, "state": initial_state})

@app.route('/api/vote', methods=['POST'])
def cast_vote():
    """
    Main endpoint for casting a vote. This function demonstrates multiple concepts.
    """
    log = []
    state = get_system_state()
    if not state: return jsonify({"error": "System not initialized."}), 500

    # DEMONSTRATES: Experiment 1 - Client-Server Communication (RPC Simulation)
    log.append("[RPC-SIM] Received vote request from client.")
    
    # DEMONSTRATES: Experiment 3 - Clock Synchronization (Logical Clock)
    state['global_lamport_clock'] += 1
    log.append(f"[CLOCK L:{state['global_lamport_clock']}] Lamport clock incremented for vote event.")

    # DEMONSTRATES: Experiment 6 - Load Balancing (Algorithm Simulation)
    state['request_counter'] += 1
    target_node_index = (state['request_counter'] - 1) % NUM_NODES + 1
    target_node_id = f'node-{target_node_index}'
    log.append(f"[LOAD BALANCER] Request #{state['request_counter']}. Round-robin chose {target_node_id} as target.")
    
    # Check for a leader; if none, trigger an election.
    leader_id, _ = get_leader(state['nodes'])
    if not leader_id:
        log.append("[LEADER CHECK] Leader is down!")
        state['nodes'] = run_leader_election(state['nodes'], log)
        leader_id, _ = get_leader(state['nodes'])
        if not leader_id:
            save_system_state(state)
            return jsonify({"log": log, "error": "No leader available to process vote."})
            
    log.append(f"[RPC-SIM] Request conceptually forwarded to leader: {leader_id}.")
    
    data = request.json
    voter_id = data.get('voterId')
    candidate = data.get('candidateName')

    if voter_id in state.get('voted_ids', []):
        log.append(f"[LEADER] Voter '{voter_id}' has already voted. Rejecting.")
        save_system_state(state)
        return jsonify({"log": log, "message": "Already voted."})

    state['voted_ids'].append(voter_id)
    log.append(f"[LEADER - {leader_id}] Vote for '{candidate}' validated and recorded.")

    # DEMONSTRATES: Experiment 5 - Data Consistency and Replication
    log.append("[REPLICATION] Replicating new vote state to all active follower nodes...")
    for node in state['nodes'].values():
        if node.get('status') == 'UP':
            node['votes'][candidate] = node['votes'].get(candidate, 0) + 1
    log.append("[REPLICATION] State successfully replicated across all nodes in the shared data store.")
    
    save_system_state(state)
    return jsonify({"log": log, "state": state, "message": "Vote cast successfully."})

@app.route('/api/add-candidate', methods=['POST'])
def add_candidate():
    log = []
    state = get_system_state()
    name = request.json.get('name')
    if name and name not in state.get('candidates', {}):
        # Add candidate to the main list and initialize vote count on all active nodes
        state['candidates'][name] = 0
        for node in state['nodes'].values():
            if node.get('status') == 'UP':
                node['votes'][name] = 0
        log.append(f"Admin added new candidate: {name}. Initialized on all nodes.")
    else:
        log.append(f"Admin action: Candidate '{name}' already exists.")
        
    save_system_state(state)
    return jsonify({"log": log, "state": state})

@app.route('/api/fail-node', methods=['POST'])
def fail_node():
    """Endpoint to simulate a node failure for leader election demonstration."""
    log = []
    state = get_system_state()
    node_id_to_fail = request.json.get('node_id')
    if node_id_to_fail in state.get('nodes', {}):
        state['nodes'][node_id_to_fail]['status'] = 'DOWN'
        state['nodes'][node_id_to_fail]['is_leader'] = False
        log.append(f"!! FAILURE SIMULATED !! Node {node_id_to_fail} has been shut down.")
        
    save_system_state(state)
    return jsonify({"log": log, "state": state})
    
@app.route('/api/get-state', methods=['GET'])
def get_state_endpoint():
    """Endpoint for the frontend to periodically poll for updates."""
    state = get_system_state()
    return jsonify(state)

# Note: The 'app = app' line is a convention for some serverless platforms, including Vercel.
app = app