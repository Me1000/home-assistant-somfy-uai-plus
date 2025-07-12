const net = require('net');

const client = new net.Socket();

client.connect(23, '10.1.1.50', () => {
    console.log('Connected to 10.1.1.50:23');
});

client.on('data', (data) => {
    console.log('Received:', JSON.stringify(data.toString()));
});

client.on('close', () => {
    console.log('Connection closed');
});

client.on('error', (err) => {
    console.error('Connection error:', err);
});