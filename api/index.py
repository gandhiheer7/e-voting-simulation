import os
import json
from flask import Flask, request, jsonify
from flask_cors import CORS
import redis
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
NUM_NODES = 3

# --- REDIS CONNECTION ---
try:
    redis_client = redis.from_url(os.getenv("REDIS_URL"))
except Exception as e:
    redis_client = None
    print(f"Could not connect to Redis: {e}")

# --- HELPER FUNCTIONS ---

def get_system_state():
    if not redis_client: return None
    state_str = redis_client.get('system_state')
    if not state_str:
        return None
    return json.loads(state_str)

def save_system_state(state):
    if not redis_client: return
    redis_client.set('system_state', json.dumps(state))

def get_leader(nodes):
    for node_id, node_info in nodes.items():
        if node_info['is_leader'] and node_info['status'] == 'UP': # FIXED: Added ==
            return node_id, node_info
    return None, None

def run_leader_election(nodes, log):
    log.append("LEADER ELECTION: Starting leader election simulation.")
    potential_leader_id = -1
    new_leader_node_id = None
    for node_id_str, node_info in nodes.items():
        if node_info['status'] == 'UP': # FIXED: Added ==
            node_num = int(node_id_str.split('-')[1])
            if node_num > potential_leader_id:
                potential_leader_id = node_num
                new_leader_node_id = node_id_str
    if new_leader_node_id:
        for node_id in nodes:
            nodes[node_id]['is_leader'] = (node_id == new_leader_node_id)
        log.append(f"LEADER ELECTION: {new_leader_node_id} is the new leader.")
    else:
        log.append("LEADER ELECTION: No available nodes to elect a leader.")
    return nodes

# --- API ROUTES ---

@app.route('/api/initialize', methods=['POST'])
def initialize_system():
    log = ["[INIT] Initializing system..."]
    initial_state = { "nodes": {}, "candidates": {}, "voted_ids": [], "global_lamport_clock": 0, "request_counter": 0 }
    for i in range(1, NUM_NODES + 1):
        node_id = f'node-{i}'
        initial_state["nodes"][node_id] = { "status": "UP", "is_leader": (i == 1), "votes": {} }
    save_system_state(initial_state)
    log.append(f"[INIT] System reset with {NUM_NODES} nodes. Node-1 is the leader.")
    return jsonify({"log": log, "state": initial_state})

@app.route('/api/vote', methods=['POST'])
def cast_vote():
    log = []
    log.append("[RPC-SIM] Received vote request from client.")
    state = get_system_state()
    if not state: return jsonify({"error": "System not initialized. Please reset."}), 500
    state['global_lamport_clock'] += 1
    log.append(f"[CLOCK L:{state['global_lamport_clock']}] Lamport clock incremented.")
    state['request_counter'] += 1
    target_node_index = (state['request_counter'] - 1) % NUM_NODES + 1
    target_node_id = f'node-{target_node_index}'
    log.append(f"[LOAD BALANCER] Request #{state['request_counter']}. Round-robin chose {target_node_id}.")
    leader_id, leader_info = get_leader(state['nodes'])
    if not leader_id:
        log.append("[LEADER CHECK] Leader is down!")
        state['nodes'] = run_leader_election(state['nodes'], log)
        leader_id, leader_info = get_leader(state['nodes'])
        if not leader_id:
            save_system_state(state)
            return jsonify({"log": log, "error": "No leader available to process vote."})
    log.append(f"[RPC-SIM] Request forwarded to leader: {leader_id}.")
    data = request.json
    voter_id = data.get('voterId')
    candidate = data.get('candidateName')
    if voter_id in state['voted_ids']:
        log.append(f"[LEADER] Voter '{voter_id}' has already voted. Rejecting.")
        save_system_state(state)
        return jsonify({"log": log, "message": "Already voted."})
    state['voted_ids'].append(voter_id)
    log.append(f"[LEADER - {leader_id}] Vote for '{candidate}' recorded.")
    log.append("[REPLICATION] Replicating new vote state to all UP follower nodes...")
    for node_id, node_info in state['nodes'].items():
        if node_info['status'] == 'UP': # FIXED: Added ==
            node_info['votes'][candidate] = node_info['votes'].get(candidate, 0) + 1
    log.append("[REPLICATION] State successfully replicated across all active nodes in KV store.")
    save_system_state(state)
    return jsonify({"log": log, "state": state, "message": "Vote cast successfully."})

@app.route('/api/add-candidate', methods=['POST'])
def add_candidate():
    log = []
    state = get_system_state()
    name = request.json.get('name')
    if name and name not in state['candidates']:
        state['candidates'][name] = 0
        log.append(f"Admin added new candidate: {name}")
    save_system_state(state)
    return jsonify({"log": log, "state": state})

@app.route('/api/fail-node', methods=['POST'])
def fail_node():
    log = []
    state = get_system_state()
    node_id_to_fail = request.json.get('node_id')
    if node_id_to_fail in state['nodes']:
        state['nodes'][node_id_to_fail]['status'] = 'DOWN'
        state['nodes'][node_id_to_fail]['is_leader'] = False
        log.append(f"!! FAILURE SIMULATED !! Node {node_id_to_fail} has been shut down.")
    save_system_state(state)
    return jsonify({"log": log, "state": state})

@app.route('/api/get-state', methods=['GET'])
def get_state_endpoint():
    state = get_system_state()
    return jsonify(state)

app = app