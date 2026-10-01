import { PageHeader } from "@/components/ui/primitives";
import ProfileForm from "@/components/profiles/ProfileForm";
export default function NewProfile() {
  return (
    <>
      <PageHeader
        title="Create profile"
        description="Describe the opportunities you want to find."
      />
      <ProfileForm />
    </>
  );
}
