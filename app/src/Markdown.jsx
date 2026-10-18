import React from 'react';
import ReactMarkdown from 'react-markdown';
import { safeLink } from './format.js';

// Briefs cite news, jobs and events by reference; a bare reference reads as "Source".
export default function Markdown({ children }) { const text = (children || '').replace(/^\s*•\s*/gm, '- '); return <div className="markdown"><ReactMarkdown components={{ a: props => <a {...props} href={safeLink(props.href)} target="_blank" rel="noreferrer">{typeof props.children === 'string' && /^(news|job|event)-\d+$/.test(props.children) ? 'Source' : props.children}</a> }}>{text}</ReactMarkdown></div>; }
