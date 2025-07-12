#!/usr/bin/env node

const http = require('http');

const BASE_URL = '10.1.1.50';
const PORT = 80;

function makeRequest(path) {
    return new Promise((resolve, reject) => {
        const options = {
            hostname: BASE_URL,
            port: PORT,
            path: path,
            method: 'GET'
        };

        const req = http.request(options, (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                try {
                    const jsonData = JSON.parse(data);
                    resolve(jsonData);
                } catch (error) {
                    reject(new Error(`Failed to parse JSON: ${error.message}`));
                }
            });
        });
        
        req.on('error', (error) => {
            reject(error);
        });
        
        req.end();
    });
}

async function getShadeInfo(nodeId) {
    try {
        console.log(`Querying shade information for node: ${nodeId}`);
        
        // Get device details
        const deviceInfo = await makeRequest(`/somfy_device.json?${nodeId}`);
        console.log('\n=== Device Information ===');
        console.log(JSON.stringify(deviceInfo, null, 2));
        
        // Get presets
        const presetInfo = await makeRequest(`/somfy_presets.json?${nodeId}`);
        console.log('\n=== Preset Information ===');
        console.log(JSON.stringify(presetInfo, null, 2));
        
    } catch (error) {
        console.error('Error querying shade:', error.message);
    }
}

async function listAllDevices() {
    try {
        console.log('Getting list of all devices...');
        const devices = await makeRequest('/somfy_devices.json');
        console.log('\n=== All Devices ===');
        console.log(JSON.stringify(devices, null, 2));
        return devices;
    } catch (error) {
        console.error('Error getting device list:', error.message);
    }
}

// Main function
async function main() {
    const nodeId = process.argv[2];
    
    if (!nodeId) {
        console.log('Usage: node query_shade.js <NODE_ID>');
        console.log('Example: node query_shade.js 13.2A.01');
        console.log('\nTo see all available devices, use: node query_shade.js --list');
        return;
    }
    
    if (nodeId === '--list') {
        await listAllDevices();
        return;
    }
    
    await getShadeInfo(nodeId);
}

main();