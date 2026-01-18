import axios from 'axios';

const api = axios.create({
    baseURL: 'http://localhost:8000',
    headers: {
        'Content-Type': 'application/json',
    },
});

export const fetchCases = async () => {
    const response = await api.get('/api/cases');
    return response.data;
};

export const fetchCaseDetails = async (caseId: string) => {
    const response = await api.get(`/api/cases/${caseId}`);
    return response.data;
};

export const fetchStats = async () => {
    const response = await api.get('/api/stats/dashboard');
    return response.data;
};
