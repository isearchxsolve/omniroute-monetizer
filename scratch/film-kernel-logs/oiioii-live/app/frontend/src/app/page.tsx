import type { ReactNode } from 'react'
import { Sparkles, Users, Film } from 'lucide-react'

function FeatureCard({ icon, title, description }: { icon: ReactNode; title: string; description: string }) {
  return <article className="rounded-xl border border-dark-700 p-6">
    <div className="mb-4">{icon}</div><h2 className="text-xl font-semibold">{title}</h2>
    <p>{description}</p>
  </article>
}

export default function FilmFeatures() {
  return <section className="grid gap-6 md:grid-cols-3">
    <FeatureCard icon={<Sparkles />} title="Plan a film" description="Develop a screenplay and storyboard." />
    <FeatureCard icon={<Users />} title="Coordinate production" description="Keep approved scenes and references together." />
    <FeatureCard icon={<Film />} title="Retain the delivery" description="Access your completed film through your account." />
  </section>
}
