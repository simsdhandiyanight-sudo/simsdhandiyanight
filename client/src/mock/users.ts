import { StaffUser } from '../types';

export const INITIAL_STAFF_USERS: StaffUser[] = [
  {
    id: 'usr-scanner-1',
    name: 'Devika Nair',
    email: 'gate2.scanner@aurapass.internal',
    role: 'SCANNER',
    assignedGate: 'Gate 2',
  },
  {
    id: 'usr-scanner-2',
    name: 'Rohan Deshmukh',
    email: 'gate1.scanner@aurapass.internal',
    role: 'SCANNER',
    assignedGate: 'Gate 1',
  },
  {
    id: 'usr-reg-desk',
    name: 'Sameer Sen',
    email: 'kiosk.desk@aurapass.internal',
    role: 'REGISTRATION',
    assignedGate: 'On-Spot Kiosk A',
  },
  {
    id: 'usr-admin-lead',
    name: 'Aditi Mathur',
    email: 'lead.ops@aurapass.internal',
    role: 'ADMIN',
  },
];
