import { PageHeader } from "@/components/ui/primitives";
import ProfileForm from "@/components/profiles/ProfileForm";
import { loadProfile } from "@/lib/load-profile";
export default async function EditProfile({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const profile = await loadProfile((await params).id);
  return (
    <>
      <PageHeader
        title="Edit profile"
        description="Update your preferences and save your changes."
      />
      <ProfileForm profile={profile} />
    </>
  );
}
