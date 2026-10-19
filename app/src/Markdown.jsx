import React from 'react';
import ReactMarkdown from 'react-markdown';
import { safeLink } from './format.js';

// Briefs cite news, jobs and events by reference; a bare reference reads as "Source".
// linkAction(href) can add a control after a link, such as a bookmark for a news story.
export default function Markdown({ children, linkAction }) { const text = (children || '').replace(/^\s*•\s*/gm, '- '); return <div className="markdown"><ReactMarkdown components={{ a: ({ node, ...props }) => <><a {...props} href={safeLink(props.href)} target="_blank" rel="noreferrer">{typeof props.children === 'string' && /^(news|job|event)-\d+$/.test(props.children) ? 'Source' : props.children}</a>{linkAction?.(props.href)}</> }}>{text}</ReactMarkdown></div>; }
