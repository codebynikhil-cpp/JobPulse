import ProfileForm from "@/components/profiles/ProfileForm";
import { loadProfile } from "@/lib/load-profile";
export default async function EditProfile({ params }: { params: Promise<{ id: string }> }) {
  const profile = await loadProfile((await params).id);
  return <><h1 className="mb-2 text-3xl font-bold">Edit profile</h1><p className="mb-8 text-slate-600">Update your preferences and save your changes.</p><ProfileForm profile={profile} /></>;
}
