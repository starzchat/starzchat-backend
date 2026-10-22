import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { expiryLabel, relativeTime, isExpired } from './lib/format.js';
import { decodeAttachment, encodeAttachment } from './lib/attachments.js';
import { upsertMessage, useStore } from './store.js';
import MessageBody from './components/MessageBody.jsx';
import AuthScreen from './components/AuthScreen.jsx';

const now = new Date('2026-10-22T12:00:00Z');

describe('format', () => {
  it('labels expiry', () => {
    expect(expiryLabel('2026-10-22T12:30:00Z', now)).toBe('30m');
    expect(expiryLabel('2026-10-23T12:00:00Z', now)).toBe('24h');
    expect(expiryLabel('2026-10-22T11:00:00Z', now)).toBe('expired');
    expect(isExpired('2026-10-22T11:00:00Z', now)).toBe(true);
  });
  it('formats relative time', () => {
    expect(relativeTime('2026-10-22T11:58:00Z', now)).toBe('2 minutes ago');
    expect(relativeTime('2026-10-22T11:59:50Z', now)).toBe('just now');
  });
});

describe('attachments', () => {
  it('round-trips and rejects non-https urls', () => {
    const s = encodeAttachment({ url: 'https://r2.example/a.pdf', name: 'a.pdf', type: 'application/pdf', size: 3 });
    expect(decodeAttachment(s).name).toBe('a.pdf');
    expect(decodeAttachment(encodeAttachment({ url: 'javascript:alert(1)', name: 'x' }))).toBeNull();
    expect(decodeAttachment('hello')).toBeNull();
    expect(decodeAttachment('::file::{bad')).toBeNull();
  });
});

describe('store', () => {
  it('upserts messages idempotently, oldest first', () => {
    let l = upsertMessage([], { id: 2 });
    l = upsertMessage(l, { id: 1 });
    l = upsertMessage(l, { id: 2, body: 'x' });
    expect(l.map((m) => m.id)).toEqual([1, 2]);
    expect(l[1].body).toBe('x');
  });
  it('removes expired messages', () => {
    useStore.setState({ messages: { 1: [{ id: 1, expires_at: '2026-10-22T11:00:00Z' }, { id: 2, expires_at: '2026-10-22T13:00:00Z' }] } });
    useStore.getState().removeExpired(now);
    expect(useStore.getState().messages[1].map((m) => m.id)).toEqual([2]);
  });
  it('receiveMessage bumps unread for inactive chats and dedupes', () => {
    useStore.setState({ me: { username: 'me' }, activeId: 9, messages: {}, chats: [{ id: 1, last_message_at: null, unread_count: 0 }] });
    const m = { id: 5, conversation_id: 1, sender: 'bob', body: 'hi', created_at: '2026-10-22T12:00:00Z', expires_at: '2026-10-23T12:00:00Z' };
    useStore.getState().receiveMessage(m);
    useStore.getState().receiveMessage(m);
    expect(useStore.getState().messages[1]).toHaveLength(1);
    expect(useStore.getState().chats[0].unread_count).toBe(2);
  });
});

describe('components', () => {
  it('escapes HTML in message bodies', () => {
    const { container } = render(<MessageBody body={'<img src=x onerror=alert(1)><b>hi</b>'} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('b')).toBeNull();
    expect(container.textContent).toContain('<b>hi</b>');
  });
  it('renders an attachment card', () => {
    render(<MessageBody body={encodeAttachment({ url: 'https://r2.example/a.pdf', name: 'a.pdf', type: 'application/pdf', size: 1 })} />);
    expect(screen.getByText('a.pdf')).toBeInTheDocument();
  });
  it('submits login with trimmed username', async () => {
    const authenticate = vi.fn().mockResolvedValue();
    useStore.setState({ authenticate });
    render(<AuthScreen />);
    fireEvent.change(screen.getByPlaceholderText('Username'), { target: { value: ' alice ' } });
    fireEvent.change(screen.getByPlaceholderText('Password (min 8)'), { target: { value: 'password1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }));
    await waitFor(() => expect(authenticate).toHaveBeenCalledWith('login', { username: 'alice', password: 'password1' }));
  });
});
