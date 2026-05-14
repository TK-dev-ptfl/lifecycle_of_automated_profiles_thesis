import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Button } from '../components/ui/Button'
import { Badge } from '../components/ui/Badge'
import { StatusDot } from '../components/ui/StatusDot'
import { KpiCard } from '../components/ui/KpiCard'
import { Card } from '../components/ui/Card'
import { Modal } from '../components/ui/Modal'
import { Input } from '../components/ui/Input'
import { Tabs } from '../components/ui/Tabs'

describe('Button', () => {
  it('renders children', () => {
    render(<Button>Click me</Button>)
    expect(screen.getByRole('button', { name: 'Click me' })).toBeInTheDocument()
  })

  it('shows loading spinner when loading', () => {
    const { container } = render(<Button loading>Loading</Button>)
    expect(container.querySelector('svg.animate-spin')).toBeInTheDocument()
  })

  it('is disabled when loading', () => {
    render(<Button loading>Loading</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('is disabled when disabled prop is true', () => {
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('calls onClick', () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Click</Button>)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('applies danger variant styles', () => {
    const { container } = render(<Button variant="danger">Delete</Button>)
    expect(container.firstChild).toHaveClass('bg-red-600')
  })
})

describe('Badge', () => {
  it('renders label', () => {
    render(<Badge label="running" />)
    expect(screen.getByText('running')).toBeInTheDocument()
  })

  it('applies success variant', () => {
    const { container } = render(<Badge variant="success" label="ok" />)
    expect(container.firstChild).toHaveClass('bg-emerald-900/60')
  })

  it('applies danger variant', () => {
    const { container } = render(<Badge variant="danger" label="error" />)
    expect(container.firstChild).toHaveClass('bg-red-900/60')
  })
})

describe('StatusDot', () => {
  it('renders running status', () => {
    const { container } = render(<StatusDot status="running" />)
    expect(container.firstChild).toHaveClass('bg-emerald-400')
  })

  it('renders banned status', () => {
    const { container } = render(<StatusDot status="banned" />)
    expect(container.firstChild).toHaveClass('bg-red-500')
  })

  it('animates when running', () => {
    const { container } = render(<StatusDot status="running" />)
    expect(container.firstChild).toHaveClass('animate-pulse')
  })

  it('does not animate when stopped', () => {
    const { container } = render(<StatusDot status="stopped" />)
    expect(container.firstChild).not.toHaveClass('animate-pulse')
  })
})

describe('KpiCard', () => {
  it('renders value and label', () => {
    render(<KpiCard value={42} label="Actions Today" />)
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('Actions Today')).toBeInTheDocument()
  })

  it('renders trend value', () => {
    render(<KpiCard value={95} label="Success Rate" trend="up" trendValue="+5%" />)
    expect(screen.getByText(/\+5%/)).toBeInTheDocument()
  })
})

describe('Card', () => {
  it('renders title and children', () => {
    render(<Card title="My Card"><p>Content here</p></Card>)
    expect(screen.getByText('My Card')).toBeInTheDocument()
    expect(screen.getByText('Content here')).toBeInTheDocument()
  })

  it('renders action button', () => {
    render(<Card title="Card" action={<button>Action</button>}><div /></Card>)
    expect(screen.getByText('Action')).toBeInTheDocument()
  })
})

describe('Modal', () => {
  it('renders when open', () => {
    render(<Modal title="Test Modal" isOpen={true} onClose={() => {}}><p>Content</p></Modal>)
    expect(screen.getByText('Test Modal')).toBeInTheDocument()
    expect(screen.getByText('Content')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<Modal title="Test Modal" isOpen={false} onClose={() => {}}><p>Content</p></Modal>)
    expect(screen.queryByText('Test Modal')).not.toBeInTheDocument()
  })

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn()
    const { container } = render(
      <Modal title="Modal" isOpen={true} onClose={onClose}><p>Content</p></Modal>
    )
    const backdrop = container.querySelector('.absolute.inset-0')
    if (backdrop) fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalled()
  })

  it('renders footer', () => {
    render(
      <Modal title="Modal" isOpen={true} onClose={() => {}} footer={<button>Confirm</button>}>
        <p>Content</p>
      </Modal>
    )
    expect(screen.getByText('Confirm')).toBeInTheDocument()
  })
})

describe('Input', () => {
  it('renders with label', () => {
    render(<Input label="Username" />)
    expect(screen.getByText('Username')).toBeInTheDocument()
  })

  it('shows error message', () => {
    render(<Input error="Required" />)
    expect(screen.getByText('Required')).toBeInTheDocument()
  })

  it('calls onChange', () => {
    const onChange = vi.fn()
    render(<Input onChange={onChange} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'test' } })
    expect(onChange).toHaveBeenCalled()
  })
})

describe('Tabs', () => {
  const tabs = [
    { id: 'stats', label: 'Stats' },
    { id: 'logs', label: 'Logs' },
  ]

  it('renders all tabs', () => {
    render(<Tabs tabs={tabs} activeTab="stats" onChange={() => {}} />)
    expect(screen.getByText('Stats')).toBeInTheDocument()
    expect(screen.getByText('Logs')).toBeInTheDocument()
  })

  it('calls onChange when tab clicked', () => {
    const onChange = vi.fn()
    render(<Tabs tabs={tabs} activeTab="stats" onChange={onChange} />)
    fireEvent.click(screen.getByText('Logs'))
    expect(onChange).toHaveBeenCalledWith('logs')
  })

  it('applies active styles to current tab', () => {
    render(<Tabs tabs={tabs} activeTab="stats" onChange={() => {}} />)
    const statsButton = screen.getByText('Stats').closest('button')
    expect(statsButton).toHaveClass('border-brand-500')
  })
})
