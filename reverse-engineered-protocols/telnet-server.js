const net = require('net');

const PORT = 23;

const server = net.createServer((socket) => {
  console.log(`Client connected: ${socket.remoteAddress}:${socket.remotePort}`);
  
  // Create connection to target server
  const targetSocket = net.createConnection({ host: '10.1.1.50', port: 23 }, () => {
    console.log('Connected to target server 10.1.1.50:23');
  });
  
  // Forward data from client to target
  socket.on('data', (data) => {
    console.log(`Client -> Target: ${data.toString().trim()}`);
    targetSocket.write(data);
  });
  
  // Forward data from target to client and log it
  targetSocket.on('data', (data) => {
    console.log(`Target -> Client: ${data.toString().trim()}`);
    socket.write(data);
  });
  
  // Handle client disconnect
  socket.on('end', () => {
    console.log(`Client disconnected: ${socket.remoteAddress}:${socket.remotePort}`);
    targetSocket.end();
  });
  
  // Handle target disconnect
  targetSocket.on('end', () => {
    console.log('Target server disconnected');
    socket.end();
  });
  
  // Handle errors
  socket.on('error', (err) => {
    console.error(`Client socket error: ${err.message}`);
    targetSocket.destroy();
  });
  
  targetSocket.on('error', (err) => {
    console.error(`Target socket error: ${err.message}`);
    socket.destroy();
  });
});

server.listen(PORT, () => {
  console.log(`Telnet server listening on port ${PORT}`);
});

server.on('error', (err) => {
  console.error(`Server error: ${err.message}`);
});