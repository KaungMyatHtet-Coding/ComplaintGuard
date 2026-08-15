const { initializeApp, cert } = require('firebase-admin/app');
const { getFirestore } = require('firebase-admin/firestore');
process.env.FIRESTORE_EMULATOR_HOST = '127.0.0.1:8185';
initializeApp({ projectId: 'demo-complaintguard' });
const db = getFirestore();
db.collection('tickets').get().then(snapshot => {
  if (snapshot.empty) {
    console.log('No tickets found.');
    return;
  }
  snapshot.forEach(doc => {
    const data = doc.data();
    console.log('--- Ticket ID:', doc.id);
    console.log('Complaint:', data.complaintText);
    console.log('Department:', data.departmentId);
    console.log('Predicted:', data.predictedDepartmentId);
    console.log('Confidence:', data.predictionConfidence);
    console.log('Status:', data.status);
    console.log('Customer:', data.customerId);
  });
}).catch(console.error);
