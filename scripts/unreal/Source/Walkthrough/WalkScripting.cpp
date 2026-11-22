#include "WalkScripting.h"
#include "Engine/World.h"

AActor* UWalkScripting::SpawnInWorld(UWorld* World, TSubclassOf<AActor> Class, const FTransform& Transform)
{
	if (!World || !Class)
	{
		return nullptr;
	}
	FActorSpawnParameters Params;
	// Meshes overlap by design (walls, floors, furniture): never refuse a spawn because of collision.
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	return World->SpawnActor<AActor>(Class, Transform, Params);
}
