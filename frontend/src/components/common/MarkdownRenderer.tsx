'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Title, Text, Code, Divider, Anchor, Box } from '@mantine/core';

interface MarkdownRendererProps {
  content: string;
  isUser?: boolean;
  fontSize?: string | number;
}

export function MarkdownRenderer({ content, isUser = false, fontSize }: MarkdownRendererProps) {
  return (
    <Box
      className="markdown-content"
      style={{
        wordBreak: 'break-word',
        color: isUser ? '#ffffff' : 'inherit',
        fontSize: fontSize || '15px',
        lineHeight: 1.65,
      }}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ node, ...props }) => (
            <Title
              order={4}
              style={{
                marginTop: '16px',
                marginBottom: '8px',
                color: isUser ? '#ffffff' : 'inherit',
                fontWeight: 700,
                fontSize: '1.4em',
              }}
              {...props}
            />
          ),
          h2: ({ node, ...props }) => (
            <Title
              order={5}
              style={{
                marginTop: '14px',
                marginBottom: '6px',
                color: isUser ? '#ffffff' : 'inherit',
                fontWeight: 700,
                fontSize: '1.25em',
              }}
              {...props}
            />
          ),
          h3: ({ node, ...props }) => (
            <Title
              order={6}
              style={{
                marginTop: '12px',
                marginBottom: '6px',
                color: isUser ? '#ffffff' : 'inherit',
                fontWeight: 700,
                fontSize: '1.15em',
              }}
              {...props}
            />
          ),
          h4: ({ node, ...props }) => (
            <Text
              fw={700}
              size="sm"
              style={{
                marginTop: '8px',
                marginBottom: '4px',
                color: isUser ? '#ffffff' : 'inherit',
              }}
              {...props}
            />
          ),
          p: ({ node, ...props }) => (
            <p
              style={{
                margin: '0 0 8px 0',
                lineHeight: '1.6',
              }}
              {...props}
            />
          ),
          ul: ({ node, ...props }) => (
            <ul
              style={{
                margin: '4px 0 8px 0',
                paddingLeft: '22px',
              }}
              {...props}
            />
          ),
          ol: ({ node, ...props }) => (
            <ol
              style={{
                margin: '4px 0 8px 0',
                paddingLeft: '22px',
              }}
              {...props}
            />
          ),
          li: ({ node, ...props }) => (
            <li
              style={{
                marginBottom: '4px',
                lineHeight: '1.5',
              }}
              {...props}
            />
          ),
          hr: ({ node, ...props }) => (
            <Divider
              my="sm"
              style={{
                borderColor: isUser ? 'rgba(255, 255, 255, 0.3)' : 'var(--mantine-color-default-border)',
              }}
              {...props}
            />
          ),
          blockquote: ({ node, ...props }) => (
            <blockquote
              style={{
                borderLeft: isUser
                  ? '3px solid rgba(255, 255, 255, 0.6)'
                  : '3px solid var(--mantine-color-blue-filled)',
                paddingLeft: '12px',
                margin: '8px 0',
                opacity: 0.9,
                fontStyle: 'italic',
              }}
              {...props}
            />
          ),
          code({ node, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const codeString = String(children).replace(/\n$/, '');
            const isMultiLine = codeString.includes('\n');
            const isInline = !match && !isMultiLine;

            if (isInline) {
              return (
                <Code
                  style={{
                    backgroundColor: isUser ? 'rgba(255, 255, 255, 0.2)' : undefined,
                    color: isUser ? '#ffffff' : undefined,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '0.85em',
                  }}
                  {...props}
                >
                  {children}
                </Code>
              );
            }

            return (
              <Code
                block
                style={{
                  margin: '8px 0',
                  fontSize: '0.9em',
                  borderRadius: '6px',
                  overflowX: 'auto',
                }}
                {...props}
              >
                {codeString}
              </Code>
            );
          },
          strong: ({ node, ...props }) => (
            <strong style={{ fontWeight: 700 }} {...props} />
          ),
          a: ({ node, href, children, ...props }) => (
            <Anchor
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              c={isUser ? 'white' : 'blue'}
              style={{ textDecoration: 'underline' }}
              {...props}
            >
              {children}
            </Anchor>
          ),
          table: ({ node, ...props }) => (
            <Box style={{ overflowX: 'auto', margin: '8px 0' }}>
              <table
                style={{
                  borderCollapse: 'collapse',
                  width: '100%',
                  fontSize: '0.92em',
                  border: isUser
                    ? '1px solid rgba(255,255,255,0.3)'
                    : '1px solid var(--mantine-color-default-border)',
                }}
                {...props}
              />
            </Box>
          ),
          th: ({ node, ...props }) => (
            <th
              style={{
                border: isUser
                  ? '1px solid rgba(255,255,255,0.3)'
                  : '1px solid var(--mantine-color-default-border)',
                padding: '6px 10px',
                textAlign: 'left',
                backgroundColor: isUser
                  ? 'rgba(255, 255, 255, 0.1)'
                  : 'var(--mantine-color-default-hover)',
                fontWeight: 600,
              }}
              {...props}
            />
          ),
          td: ({ node, ...props }) => (
            <td
              style={{
                border: isUser
                  ? '1px solid rgba(255,255,255,0.3)'
                  : '1px solid var(--mantine-color-default-border)',
                padding: '6px 10px',
              }}
              {...props}
            />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </Box>
  );
}

export default MarkdownRenderer;
