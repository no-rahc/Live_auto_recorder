import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './App';
import { RouterProvider } from './router';
import './style.css';
const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { refetchOnWindowFocus: true } } });
createRoot(document.getElementById('root')!).render(<StrictMode><QueryClientProvider client={queryClient}><RouterProvider><App/></RouterProvider></QueryClientProvider></StrictMode>);
