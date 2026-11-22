#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "WalkGameMode.generated.h"

/** Spawns AWalkCharacter at the level's player start. Set it as GlobalDefaultGameMode in DefaultEngine.ini. */
UCLASS()
class WALKTHROUGH_API AWalkGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AWalkGameMode();
};
