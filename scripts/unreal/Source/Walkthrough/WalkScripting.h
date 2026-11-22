#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "WalkScripting.generated.h"

/**
 * Helpers for Content/Python/import_manifest.py. The editor scripting subsystems refuse to spawn actors in a
 * commandlet (UnrealEditor-Cmd -run=pythonscript), so the level build spawns through this function.
 * Python: unreal.WalkScripting.spawn_in_world(world, cls, transform)
 */
UCLASS()
class WALKTHROUGH_API UWalkScripting : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "Walkthrough")
	static AActor* SpawnInWorld(UWorld* World, TSubclassOf<AActor> Class, const FTransform& Transform);
};
