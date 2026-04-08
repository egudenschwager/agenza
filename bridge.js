const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');
const express = require('express');

const app = express();
app.use(express.json());

// 1. Inicializar cliente con sesión guardada (para no escanear el QR cada vez)
const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: { args: ['--no-sandbox', '--disable-setuid-sandbox'] } // Vital para que funcione en Ubuntu
});

// 2. Generar el QR en la terminal
client.on('qr', (qr) => {
    console.log('\n=========================================');
    console.log('📱 ESCANEA ESTE QR CON TU WHATSAPP (Dispositivos Vinculados):');
    qrcode.generate(qr, { small: true });
    console.log('=========================================\n');
});

client.on('ready', () => {
    console.log('✅ Puente WhatsApp conectado y operando con éxito!');
});

// 3. Cuando entra un mensaje, lo mandamos a tu FastAPI
client.on('message', async msg => {
    if (msg.from === 'status@broadcast') return; // Ignorar estados

    console.log(`📩 Recibido: ${msg.body}`);

    try {
        await axios.post('http://127.0.0.1:8000/webhook', {
            type: 'whatsapp',
            from: msg.from.replace('@c.us', ''),
            name: msg._data.notifyName || 'Paciente',
            text: msg.body
        });
    } catch (error) {
        console.error('❌ Error enviando a FastAPI. ¿Está corriendo Uvicorn?');
    }
});

client.initialize();

// 4. Endpoint local para que FastAPI nos pida enviar respuestas
app.post('/send', async (req, res) => {
    const { number, text } = req.body;
    try {
        const chatId = number.includes('@') ? number : `${number}@c.us`;
        await client.sendMessage(chatId, text);
        res.status(200).send({ status: 'ok' });
    } catch (error) {
        console.error('❌ Error enviando mensaje a WP:', error.message);
        res.status(500).send({ error: error.message });
    }
});

app.listen(3000, () => {
    console.log('🚀 Puente escuchando peticiones de Python en el puerto 3000');
});
