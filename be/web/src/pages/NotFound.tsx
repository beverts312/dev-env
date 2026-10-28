import { Link } from 'react-router'

export function NotFound() {
  return (
    <p className="text-sm text-muted-foreground">
      Nothing here.{' '}
      <Link to="/" className="text-primary hover:underline">
        Back to my work
      </Link>
    </p>
  )
}
