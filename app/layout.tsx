import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Benter 賽馬量化分析系統',
  description: 'Bill Benter Model - Softmax + Kelly Criterion',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-HK">
      <body>
        {children}
      </body>
    </html>
  )
}
